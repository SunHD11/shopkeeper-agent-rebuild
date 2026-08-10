"""
字段召回节点。

负责把用户问题中的业务表达映射到 DW MySQL 中可能相关的真实字段。

处理链路：

    query + 公共 keywords
        -> 字段语义扩展 Prompt
        -> Embedding
        -> 字段 Qdrant Collection
        -> ColumnInfo 按业务 id 去重
        -> retrieved_column_infos

本节点只扩大候选范围，不决定最终使用哪些字段；候选字段会继续交给
merge_retrieved_info 补齐表关系，再由 filter_table 做最终裁剪。
"""

import asyncio

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt


async def recall_column(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[ColumnInfo]]:
    """召回与用户问题语义相关的字段业务实体。"""

    # stream_writer 会把节点执行状态交给 QueryService，后续再通过 SSE
    # 实时显示在前端步骤列表中。
    writer = runtime.stream_writer
    step = "召回字段信息"
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # query 是完整原问题，用于让 LLM 从整体语义推断必需字段；
        # keywords 是 extract_keywords 生成的公共检索入口。
        query = state["query"]
        keywords = state["keywords"]

        # 外部工具从 Context 获取，不能放入需要被合并或持久化的 State。
        embedding_client = runtime.context["embedding_client"]
        column_qdrant_repository = runtime.context["column_qdrant_repository"]

        # 字段扩展 Prompt 只允许输出 JSON 字符串数组。
        # 例如“最近三个月华东销售额”可能扩展为：
        # ["订单时间", "地区", "订单金额"]。
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()

        # LCEL 管道依次完成：填充 Prompt -> 调用 LLM -> 解析 JSON。
        chain = prompt | llm | output_parser
        expanded_keywords: list[str] = await chain.ainvoke({"query": query})

        # 公共关键词保留用户原始用词，字段扩展词补充隐含 Schema 概念；
        # set 去掉两组关键词之间的重复项。召回逻辑不依赖遍历顺序。
        all_keywords = set(keywords + expanded_keywords)

        # 离线构建时，同一字段的名称、描述和每个别名分别形成 Qdrant Point；
        # 在线多个关键词也可能命中同一字段，所以必须按 ColumnInfo.id 去重，
        # 不能按每个 Point 的 UUID 去重。
        column_info_map: dict[str, ColumnInfo] = {}

        for keyword in all_keywords:
            # Qdrant 执行向量相似度搜索，因此每个文本关键词要先使用与离线构建
            # 相同的 Embedding 模型转换成相同维度的查询向量。
            async with asyncio.timeout(app_config.runtime.retrieval_timeout_seconds):
                embedding = await embedding_client.aembed_query(keyword)

                # Repository 封装 Collection 名称、阈值、查询参数和 Payload 转实体；
                # 节点只表达“使用这个向量搜索字段”的业务意图。
                current_column_infos: list[
                    ColumnInfo
                ] = await column_qdrant_repository.search(embedding)

            for column_info in current_column_infos:
                if column_info.id not in column_info_map:
                    column_info_map[column_info.id] = column_info

        retrieved_column_infos = list(column_info_map.values())
        retrieved_column_ids = [
            column_info.id for column_info in retrieved_column_infos
        ]
        logger.info(f"召回字段成功: {retrieved_column_ids}")

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )

        # 返回局部 State 更新。LangGraph 会把它与 query、keywords 等已有字段合并。
        return {"retrieved_column_infos": retrieved_column_infos}

    except Exception as error:
        # LLM、JSON 解析、Embedding 或 Qdrant 任一步失败都不能伪装成空召回，
        # 否则后续模型可能在没有真实 Schema 的情况下编造数据库字段。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
