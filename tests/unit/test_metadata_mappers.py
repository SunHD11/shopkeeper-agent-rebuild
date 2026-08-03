"""测试元数据实体与 ORM 模型之间的转换。"""

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.models.column_info import ColumnInfoMySQL
from app.models.column_metric import ColumnMetricMySQL
from app.models.metric_info import MetricInfoMySQL
from app.models.table_info import TableInfoMySQL
from app.repositories.mysql.meta.mappers.column_info_mapper import ColumnInfoMapper
from app.repositories.mysql.meta.mappers.column_metric_mapper import (
    ColumnMetricMapper,
)
from app.repositories.mysql.meta.mappers.metric_info_mapper import MetricInfoMapper
from app.repositories.mysql.meta.mappers.table_info_mapper import TableInfoMapper


def test_table_info_mapper_round_trip() -> None:
    """表实体转换成 ORM 后还能还原成相同实体。"""

    entity = TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )

    model = TableInfoMapper.to_model(entity)
    restored = TableInfoMapper.to_entity(model)

    assert isinstance(model, TableInfoMySQL)
    assert restored == entity


def test_column_info_mapper_round_trip() -> None:
    """字段实体转换成 ORM 后还能还原成相同实体。"""

    entity = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0, 268.0],
        description="订单金额。",
        alias=["销售额", "收入"],
        table_id="fact_order",
    )

    model = ColumnInfoMapper.to_model(entity)
    restored = ColumnInfoMapper.to_entity(model)

    assert isinstance(model, ColumnInfoMySQL)
    assert restored == entity


def test_metric_info_mapper_round_trip() -> None:
    """指标实体转换成 ORM 后还能还原成相同实体。"""

    entity = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    model = MetricInfoMapper.to_model(entity)
    restored = MetricInfoMapper.to_entity(model)

    assert isinstance(model, MetricInfoMySQL)
    assert restored == entity


def test_column_metric_mapper_round_trip() -> None:
    """字段指标关系能够在实体与 ORM 之间双向转换。"""

    entity = ColumnMetric(
        column_id="fact_order.order_amount",
        metric_id="GMV",
    )

    model = ColumnMetricMapper.to_model(entity)
    restored = ColumnMetricMapper.to_entity(model)

    assert isinstance(model, ColumnMetricMySQL)
    assert restored == entity
