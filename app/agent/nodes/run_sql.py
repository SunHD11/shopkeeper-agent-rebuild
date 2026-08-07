"""
最终 SQL 执行节点。

本节点接收已经通过校验的候选 SQL，或由 ``correct_sql`` 覆盖后的修正 SQL，
通过 DW Repository 执行查询，并使用自定义流式事件把结果返回给上层调用方。
执行完成后 LangGraph 进入 END。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def run_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> None:
    """执行最终 SQL，并通过 stream_writer 输出普通字典列表结果。"""

    writer = runtime.stream_writer
    step = "执行SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        sql = state["sql"]
        if not sql.strip():
            raise ValueError("待执行 SQL 不能为空")

        dw_mysql_repository = runtime.context["dw_mysql_repository"]

        # Repository 封装 SQLAlchemy execute、mappings 和 RowMapping 转 dict；
        # 节点只表达“执行这条最终查询”的业务意图。
        result = await dw_mysql_repository.run(sql)

        logger.info(f"SQL 执行结果: {result}")
        writer({"type": "progress", "step": step, "status": "success"})

        # 查询结果不是下一节点需要继续推理的 State，而是整个问数任务的最终
        # 对外输出，因此通过自定义 result 事件直接交给 QueryService/前端。
        writer({"type": "result", "data": result})

    except Exception as error:
        logger.error(f"{step}失败: {error}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
