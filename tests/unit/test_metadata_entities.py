"""测试元数据业务实体。"""

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo


def test_table_and_column_entities() -> None:
    """表实体和字段实体能够表达完整字段元数据。"""

    table = TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )

    column = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0, 268.0],
        description="订单金额。",
        alias=["销售额", "收入"],
        table_id=table.id,
    )

    assert table.id == "fact_order"
    assert column.table_id == table.id
    assert column.alias == ["销售额", "收入"]
    assert column.examples == [100.0, 268.0]


def test_metric_and_column_metric_entities() -> None:
    """指标实体能够通过关系实体关联到底层字段。"""

    metric = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    relationship = ColumnMetric(
        column_id="fact_order.order_amount",
        metric_id=metric.id,
    )

    assert relationship.column_id in metric.relevant_columns
    assert relationship.metric_id == metric.id


def test_value_entity_points_to_its_column() -> None:
    """字段值实体能够记录真实值及其所属字段。"""

    value = ValueInfo(
        id="dim_region.region_name.华东",
        value="华东",
        column_id="dim_region.region_name",
    )

    assert value.value == "华东"
    assert value.column_id == "dim_region.region_name"
