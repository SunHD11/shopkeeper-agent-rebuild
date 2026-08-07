"""
SQL 生成前的额外上下文补全节点。

表、字段和指标来自在线 RAG 检索链路，但有些生成 SQL 必需的信息并不属于
元数据知识库，例如当前日期、数据库方言和数据库版本。本节点统一补齐这些
运行环境事实，让后续模型能够正确处理相对时间和方言相关语法。

处理链路：

    系统当前日期 -> date_info
    DW MySQL 环境 -> db_info
    date_info + db_info -> 写回 DataAgentState

本节点不调用 LLM，也不访问 Qdrant、Elasticsearch 或 Meta MySQL。
"""

from datetime import date

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState, DateInfoState, DBInfoState
from app.core.log import logger


async def add_extra_context(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, DateInfoState | DBInfoState]:
    """补齐 SQL 生成所需的日期和目标数据库环境信息。"""

    # state 当前没有被直接读取，但保留统一的 LangGraph 节点签名。
    # 在图执行时，LangGraph 会始终向节点传入当前 State 和 Runtime。
    _ = state

    writer = runtime.stream_writer
    step = "添加额外上下文"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # DW Repository 是目标 SQL 最终校验和执行的数据库入口，因此数据库
        # 方言与版本也必须从它读取，而不是在代码中写死为 mysql/8.x。
        dw_mysql_repository = runtime.context["dw_mysql_repository"]

        # 当前日期是解释“今天、本周、本月、本季度、最近 N 天”等相对时间
        # 表达的计算基准。DateInfoState 使用简单字符串，便于序列化进 Prompt。
        today = date.today()
        date_string = today.strftime("%Y-%m-%d")
        weekday = today.strftime("%A")

        # 月份 1~3 -> Q1，4~6 -> Q2，7~9 -> Q3，10~12 -> Q4。
        # 例如 8 月：(8 - 1) // 3 + 1 = 3，因此属于 Q3。
        quarter = f"Q{(today.month - 1) // 3 + 1}"
        date_info = DateInfoState(
            date=date_string,
            weekday=weekday,
            quarter=quarter,
        )

        # get_db_info() 会执行 SELECT VERSION()，并从 SQLAlchemy Engine 读取
        # dialect.name。不同数据库和版本的日期函数、分页和类型转换语法不同。
        database_info = await dw_mysql_repository.get_db_info()
        dialect = database_info.get("dialect")
        version = database_info.get("version")

        # Repository 的底层查询类型允许 version 为 None；但 Prompt 中的 DBInfo
        # 必须完整，否则模型无法可靠决定 SQL 语法，所以在此处快速失败。
        if not isinstance(dialect, str) or not dialect:
            raise ValueError("DW MySQL 未返回有效的数据库方言")
        if not isinstance(version, str) or not version:
            raise ValueError("DW MySQL 未返回有效的数据库版本")

        db_info = DBInfoState(
            dialect=dialect,
            version=version,
        )

        logger.info(f"数据库信息: {db_info}")
        logger.info(f"日期信息: {date_info}")
        writer({"type": "progress", "step": step, "status": "success"})

        # LangGraph 会把这两个局部字段合并回 State；过滤后的 table_infos 和
        # metric_infos 不会被本节点覆盖。
        return {
            "date_info": date_info,
            "db_info": db_info,
        }

    except Exception as error:
        logger.error(f"{step}失败: {error}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
