"""
候选 SQL 数据库校验节点。

LLM 生成的 SQL 必须交给真实 DW MySQL 解析。Repository 使用 ``EXPLAIN``
检查语法、表名、字段名和 JOIN 是否能够被数据库接受，但不会执行完整业务查询。

校验失败属于预期业务分支，不会直接终止 Graph；错误文本会写入 ``state["error"]``，
由条件边决定进入 ``correct_sql``。节点自身故障才会发送 error 并抛出异常。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


async def validate_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, str | None]:
    """使用真实 DW MySQL 校验 SQL，并返回控制条件分支的 error。"""

    writer = runtime.stream_writer
    step = "校验SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # sql 可能来自 generate_sql，也可能在未来扩展循环校正时来自 correct_sql。
        sql = state["sql"]
        if not sql.strip():
            raise ValueError("待校验 SQL 不能为空")

        dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

        try:
            # Repository 内部执行 EXPLAIN <sql>。成功时无需返回数据，只表示
            # 数据库能够解析这条查询。
            await dw_mysql_repository.validate(sql)

        except Exception as validation_error:
            # SQL 无法被数据库解析是校验节点正常完成的一种结果，不是节点崩溃。
            # 因此进度仍发送 success，同时把错误写入 State，交给 Graph 分流。
            error_message = str(validation_error)
            logger.info(f"SQL 校验未通过: {error_message}")
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": error_message}

        logger.info("SQL 校验通过")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"error": None}

    except Exception as error:
        # State 缺失、SQL 为空、Context 配置错误等属于节点自身无法完成校验，
        # 与“数据库正常返回 SQL 语法错误”不同，因此这里报告 error 并终止图。
        logger.error(f"{step}失败: {error}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
