"""测试在线问数 Agent 在 LangGraph 节点之间传递的状态结构。"""

from app.agent.state import (
    ColumnInfoState,
    DataAgentState,
    DateInfoState,
    DBInfoState,
    MetricInfoState,
    TableInfoState,
)
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


def test_table_state_can_nest_prompt_facing_column_state() -> None:
    """表上下文能够按照“表 -> 字段列表”组织 SQL 生成所需信息。"""

    # ColumnInfoState 不是数据库 ORM，也不是完整的 ColumnInfo 实体；
    # 它只保留过滤表结构和生成 SQL 时真正需要交给大模型的字段信息。
    column = ColumnInfoState(
        name="order_amount",
        type="float",
        role="measure",
        examples=[100.0, 268.0],
        description="订单最终成交金额。",
        alias=["销售额", "成交金额"],
    )

    # Meta MySQL 中表和字段通过 table_id 分开保存；进入 Agent State 后，
    # merge_retrieved_info 会把它们组织成更适合 Prompt 阅读的嵌套结构。
    table = TableInfoState(
        name="fact_order",
        role="fact",
        description="记录订单金额、数量和关联维度的订单事实表。",
        columns=[column],
    )

    assert table["name"] == "fact_order"
    assert table["columns"][0]["name"] == "order_amount"
    assert table["columns"][0]["examples"] == [100.0, 268.0]
    assert table["columns"][0]["alias"] == ["销售额", "成交金额"]


def test_metric_state_preserves_business_definition() -> None:
    """指标上下文能够保存名称、口径、依赖字段和别名。"""

    metric = MetricInfoState(
        name="GMV",
        description="所有有效订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    # relevant_columns 会约束 SQL 生成使用正确的底层字段，
    # alias 则负责把用户说法映射到标准指标名称。
    assert metric["name"] == "GMV"
    assert metric["relevant_columns"] == ["fact_order.order_amount"]
    assert "成交总额" in metric["alias"]


def test_extra_context_describes_date_and_database_environment() -> None:
    """日期与数据库子状态能够提供相对时间和 SQL 方言上下文。"""

    date_info = DateInfoState(
        date="2026-08-06",
        weekday="Thursday",
        quarter="Q3",
    )
    db_info = DBInfoState(
        dialect="mysql",
        version="8.0.36",
    )

    assert date_info["quarter"] == "Q3"
    assert db_info == {"dialect": "mysql", "version": "8.0.36"}


def test_data_agent_state_can_start_with_only_the_user_query() -> None:
    """一次图执行可以从只有 query 的初始状态开始。"""

    # TypedDict 在运行时仍然是普通字典，不会强制要求一次填完所有字段。
    # QueryService 按原项目流程只写入 query，后续节点再返回局部更新，
    # LangGraph 会把 keywords、召回结果和 SQL 等字段逐步合并进 State。
    state = DataAgentState(query="查询华东地区最近三个月的销售总额")

    assert state == {"query": "查询华东地区最近三个月的销售总额"}
    assert "keywords" not in state
    assert "sql" not in state


def test_data_agent_state_can_represent_the_complete_query_pipeline() -> None:
    """总状态能够承载召回、合并、SQL 生成和校验阶段的完整数据。"""

    # 三路 Repository 返回的是稳定的业务实体，而不是底层存储系统的原始结果。
    column_entity = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="float",
        role="measure",
        examples=[100.0],
        description="订单成交金额。",
        alias=["销售额"],
        table_id="fact_order",
    )
    metric_entity = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有有效订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额"],
    )
    value_entity = ValueInfo(
        id="dim_region.region_name.华东",
        value="华东",
        column_id="dim_region.region_name",
    )

    column_state = ColumnInfoState(
        name="order_amount",
        type="float",
        role="measure",
        examples=[100.0],
        description="订单成交金额。",
        alias=["销售额"],
    )
    table_state = TableInfoState(
        name="fact_order",
        role="fact",
        description="订单事实表。",
        columns=[column_state],
    )
    metric_state = MetricInfoState(
        name="GMV",
        description="所有有效订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额"],
    )

    state = DataAgentState(
        query="查询华东地区的销售总额",
        keywords=["华东", "销售总额"],
        retrieved_column_infos=[column_entity],
        retrieved_metric_infos=[metric_entity],
        retrieved_value_infos=[value_entity],
        table_infos=[table_state],
        metric_infos=[metric_state],
        date_info=DateInfoState(
            date="2026-08-06",
            weekday="Thursday",
            quarter="Q3",
        ),
        db_info=DBInfoState(dialect="mysql", version="8.0.36"),
        sql="SELECT SUM(order_amount) AS GMV FROM fact_order",
        error=None,
    )

    assert state["retrieved_column_infos"][0] is column_entity
    assert state["retrieved_metric_infos"][0].name == "GMV"
    assert state["retrieved_value_infos"][0].value == "华东"
    assert state["table_infos"][0]["columns"][0]["name"] == "order_amount"
    assert state["metric_infos"][0]["relevant_columns"] == ["fact_order.order_amount"]
    assert state["db_info"]["dialect"] == "mysql"
    assert state["sql"].startswith("SELECT")
    assert state["error"] is None


def test_data_agent_state_can_carry_a_sql_validation_error() -> None:
    """SQL 校验失败时，error 字段能够保存数据库返回的错误信息。"""

    # validate_sql 成功时写入 None，失败时写入字符串；
    # Graph 会根据这个字段选择 run_sql 或 correct_sql 分支。
    state = DataAgentState(
        query="查询销售额",
        keywords=[],
        retrieved_column_infos=[],
        retrieved_metric_infos=[],
        retrieved_value_infos=[],
        table_infos=[],
        metric_infos=[],
        date_info=DateInfoState(
            date="2026-08-06",
            weekday="Thursday",
            quarter="Q3",
        ),
        db_info=DBInfoState(dialect="mysql", version="8.0.36"),
        sql="SELECT order_money FROM fact_order",
        error="Unknown column 'order_money'",
    )

    assert state["error"] == "Unknown column 'order_money'"
