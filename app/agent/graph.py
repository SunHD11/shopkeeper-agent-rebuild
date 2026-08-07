"""
电商自然语言问数 Agent 的 LangGraph 图编排。

这个模块不实现具体检索或 SQL 逻辑，而是声明：

- 哪些节点存在；
- 节点按照什么顺序执行；
- 哪些节点可以并行；
- 哪些节点必须等待多个前置分支全部完成；
- SQL 校验后应该进入执行分支还是修正分支。

完整链路：

    用户问题
        -> 关键词抽取
        -> 字段 / 指标 / 字段值三路并行召回
        -> 召回信息合并
        -> 表字段 / 指标并行过滤
        -> 日期和数据库环境补全
        -> SQL 生成
        -> SQL 校验
        -> 直接执行或先修正再执行
        -> END
"""

import asyncio
from typing import Literal

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.context import DataAgentContext
from app.agent.nodes.add_extra_context import add_extra_context
from app.agent.nodes.correct_sql import correct_sql
from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.nodes.fail_sql_validation import fail_sql_validation
from app.agent.nodes.filter_metric import filter_metric
from app.agent.nodes.filter_table import filter_table
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.recall_column import recall_column
from app.agent.nodes.recall_metric import recall_metric
from app.agent.nodes.recall_value import recall_value
from app.agent.nodes.run_sql import run_sql
from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def route_after_validation(
    state: DataAgentState,
) -> Literal["run_sql", "correct_sql", "fail_sql_validation"]:
    """根据 validate_sql 写入的 error 决定下一节点。

    - ``error is None``：数据库 EXPLAIN 校验通过，直接执行；
    - ``error`` 为字符串：校验失败，先把 SQL 和错误交给 LLM 修正。

    单独定义路由函数而不是使用匿名 lambda，便于阅读和单元测试。
    """

    if state["error"] is None:
        return "run_sql"

    if state.get("sql_correction_attempts", 0) >= 1:
        return "fail_sql_validation"

    return "correct_sql"


# StateGraph 声明图中所有节点共享的动态 State，以及运行时依赖 Context。
# State 保存 query、召回结果、SQL 等不断变化的数据；Context 保存 Repository、
# Embedding Client 等一次请求期间保持不变的外部工具。
graph_builder = StateGraph(
    state_schema=DataAgentState,
    context_schema=DataAgentContext,
)

# ---------------------------------------------------------------------------
# 1. 注册所有节点
# ---------------------------------------------------------------------------
#
# add_node() 只是为函数分配图中的稳定名称，还没有决定执行顺序。
graph_builder.add_node("extract_keywords", extract_keywords)
graph_builder.add_node("recall_column", recall_column)
graph_builder.add_node("recall_value", recall_value)
graph_builder.add_node("recall_metric", recall_metric)
graph_builder.add_node("merge_retrieved_info", merge_retrieved_info)
graph_builder.add_node("filter_metric", filter_metric)
graph_builder.add_node("filter_table", filter_table)
graph_builder.add_node("add_extra_context", add_extra_context)
graph_builder.add_node("generate_sql", generate_sql)
graph_builder.add_node("validate_sql", validate_sql)
graph_builder.add_node("correct_sql", correct_sql)
graph_builder.add_node("fail_sql_validation", fail_sql_validation)
graph_builder.add_node("run_sql", run_sql)

# ---------------------------------------------------------------------------
# 2. 从 START 进入关键词抽取
# ---------------------------------------------------------------------------
#
# 初始 State 通常只包含 query。extract_keywords 产生后面三路召回共用的
# keywords，因此它必须是所有检索节点之前的第一个业务节点。
graph_builder.add_edge(START, "extract_keywords")

# ---------------------------------------------------------------------------
# 3. 关键词抽取后启动三路并行召回
# ---------------------------------------------------------------------------
#
# 三个节点相互独立：
# recall_column 使用 Embedding + 字段 Qdrant；
# recall_metric 使用 Embedding + 指标 Qdrant；
# recall_value 使用 Elasticsearch 全文检索。
graph_builder.add_edge("extract_keywords", "recall_column")
graph_builder.add_edge("extract_keywords", "recall_value")
graph_builder.add_edge("extract_keywords", "recall_metric")

# ---------------------------------------------------------------------------
# 4. 等待三路召回全部完成，再执行一次合并
# ---------------------------------------------------------------------------
#
# add_edge([...], end) 是 LangGraph 的等待边：只有列表中的所有节点都完成后，
# end 节点才会执行。它比添加三条独立入边更明确，避免合并节点在每条分支完成时
# 分别被触发。此时 State 已同时拥有三个 retrieved_* 字段。
graph_builder.add_edge(
    ["recall_column", "recall_value", "recall_metric"],
    "merge_retrieved_info",
)

# ---------------------------------------------------------------------------
# 5. 合并后并行过滤候选表字段与候选指标
# ---------------------------------------------------------------------------
#
# filter_table 只更新 table_infos，filter_metric 只更新 metric_infos，二者没有
# 数据依赖，可以并行调用 LLM，缩短单次问数的总等待时间。
graph_builder.add_edge("merge_retrieved_info", "filter_table")
graph_builder.add_edge("merge_retrieved_info", "filter_metric")

# 两个过滤节点都完成后，State 中才同时存在最终表上下文和最终指标上下文。
graph_builder.add_edge(
    ["filter_table", "filter_metric"],
    "add_extra_context",
)

# ---------------------------------------------------------------------------
# 6. 补齐环境信息并生成候选 SQL
# ---------------------------------------------------------------------------
#
# add_extra_context 写入 date_info 和 db_info。到达 generate_sql 时，模型所需的
# query、table_infos、metric_infos、date_info、db_info 已全部准备完成。
graph_builder.add_edge("add_extra_context", "generate_sql")
graph_builder.add_edge("generate_sql", "validate_sql")

# ---------------------------------------------------------------------------
# 7. 根据数据库校验结果走条件分支
# ---------------------------------------------------------------------------
#
# path 调用 route_after_validation() 得到逻辑分支名；path_map 再把逻辑名称映射
# 到真实节点。当前名称相同，但显式映射可以让分支关系更清楚。
graph_builder.add_conditional_edges(
    source="validate_sql",
    path=route_after_validation,
    path_map={
        "run_sql": "run_sql",
        "correct_sql": "correct_sql",
        "fail_sql_validation": "fail_sql_validation",
    },
)

# 校验失败时只允许进行一次自动修正。修正后的 SQL 必须重新经过相同的只读
# 安全检查和数据库 EXPLAIN；第二次仍失败则进入 fail_sql_validation 明确终止。
graph_builder.add_edge("correct_sql", "validate_sql")
graph_builder.add_edge("fail_sql_validation", END)

# run_sql 通过 stream_writer 输出最终 result 事件，随后任务结束。
graph_builder.add_edge("run_sql", END)

# compile() 把声明式节点和边转换成可调用的 CompiledStateGraph。
# 外部 Service 通过 graph.astream()/graph.ainvoke() 使用它，而不是操作 builder。
graph = graph_builder.compile()


if __name__ == "__main__":

    async def test() -> None:
        """初始化 rebuild 独立基础服务依赖并运行一次完整问数链路。"""

        # init() 只创建客户端或 Engine；真实连接通常在第一次请求时建立。
        qdrant_client_manager.init()
        embedding_client_manager.init()
        es_client_manager.init()
        meta_mysql_client_manager.init()
        dw_mysql_client_manager.init()

        try:
            # rebuild 的 ClientManager 使用 require_*() 显式检查生命周期。
            # 如果忘记 init()，这里会给出清晰 RuntimeError，而不是稍后出现
            # “None 没有某某属性”的模糊错误。
            qdrant_client = qdrant_client_manager.require_client()
            embedding_client = embedding_client_manager.require_client()
            es_client = es_client_manager.require_client()
            meta_session_factory = meta_mysql_client_manager.require_session_factory()
            dw_session_factory = dw_mysql_client_manager.require_session_factory()

            # 两个 MySQL 使用完全独立的 Session：Meta MySQL 读取元数据，
            # DW MySQL 获取环境、校验 SQL 并执行最终查询。
            async with (
                meta_session_factory() as meta_session,
                dw_session_factory() as dw_session,
            ):
                context = DataAgentContext(
                    column_qdrant_repository=ColumnQdrantRepository(qdrant_client),
                    embedding_client=embedding_client,
                    metric_qdrant_repository=MetricQdrantRepository(qdrant_client),
                    value_es_repository=ValueESRepository(es_client),
                    meta_mysql_repository=MetaMySQLRepository(meta_session),
                    dw_mysql_repository=DWMySQLRepository(dw_session),
                )

                # 初始 State 只需要用户问题，其余字段由图中的节点逐步写入。
                initial_state = DataAgentState(query="统计华北地区的销售总额")

                # custom 模式只消费各节点通过 stream_writer 写出的进度和结果事件。
                async for event in graph.astream(
                    input=initial_state,
                    context=context,
                    stream_mode="custom",
                ):
                    print(event)

        finally:
            # 无论中间哪一步失败，都关闭显式创建的异步客户端和连接池。
            await qdrant_client_manager.close()
            await es_client_manager.close()
            await embedding_client_manager.close()
            await meta_mysql_client_manager.close()
            await dw_mysql_client_manager.close()

    asyncio.run(test())
