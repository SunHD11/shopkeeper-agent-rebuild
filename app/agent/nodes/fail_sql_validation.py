"""修正后的 SQL 仍未通过校验时，明确终止问数工作流。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def fail_sql_validation(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> None:
    """报告最终校验错误，防止 SQL 修正流程无限循环或带错执行。"""

    error = state.get("error") or "修正后的 SQL 未通过校验"
    message = f"SQL 自动修正一次后仍未通过校验: {error}"
    logger.error(message)
    runtime.stream_writer(
        {
            "type": "progress",
            "step": "终止SQL执行",
            "status": "error",
        }
    )
    raise ValueError(message)
