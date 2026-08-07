"""测试 Meta MySQL Repository 的实体保存和查询转换。"""

from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.models.column_info import ColumnInfoMySQL
from app.models.column_metric import ColumnMetricMySQL
from app.models.metric_info import MetricInfoMySQL
from app.models.table_info import TableInfoMySQL
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository


def test_save_table_infos() -> None:
    """表实体会转换成 TableInfoMySQL 并加入 Session。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    table_info = TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )

    repository.save_table_infos([table_info])

    models = session.add_all.call_args.args[0]
    assert len(models) == 1
    assert isinstance(models[0], TableInfoMySQL)
    assert models[0].id == "fact_order"
    assert models[0].name == "fact_order"
    assert models[0].role == "fact"
    assert models[0].description == "订单事实表。"


def test_save_column_infos() -> None:
    """字段实体会转换成 ColumnInfoMySQL 并加入 Session。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    column_info = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0, 268.0],
        description="订单金额。",
        alias=["销售额", "收入"],
        table_id="fact_order",
    )

    repository.save_column_infos([column_info])

    models = session.add_all.call_args.args[0]
    assert len(models) == 1
    assert isinstance(models[0], ColumnInfoMySQL)
    assert models[0].id == "fact_order.order_amount"
    assert models[0].type == "decimal(10,2)"
    assert models[0].examples == [100.0, 268.0]
    assert models[0].alias == ["销售额", "收入"]
    assert models[0].table_id == "fact_order"


def test_save_metric_infos() -> None:
    """指标实体会转换成 MetricInfoMySQL 并加入 Session。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    metric_info = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    repository.save_metric_infos([metric_info])

    models = session.add_all.call_args.args[0]
    assert len(models) == 1
    assert isinstance(models[0], MetricInfoMySQL)
    assert models[0].id == "GMV"
    assert models[0].description == "所有订单的成交金额总和。"
    assert models[0].relevant_columns == ["fact_order.order_amount"]
    assert models[0].alias == ["成交总额", "订单总额"]


def test_save_column_metrics() -> None:
    """字段指标关系会转换成 ColumnMetricMySQL 并加入 Session。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    relationship = ColumnMetric(
        column_id="fact_order.order_amount",
        metric_id="GMV",
    )

    repository.save_column_metrics([relationship])

    models = session.add_all.call_args.args[0]
    assert len(models) == 1
    assert isinstance(models[0], ColumnMetricMySQL)
    assert models[0].column_id == "fact_order.order_amount"
    assert models[0].metric_id == "GMV"


async def test_get_column_info_by_id() -> None:
    """查询字段 ORM 后会转换成 ColumnInfo。"""

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = ColumnInfoMySQL(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0],
        description="订单金额。",
        alias=["销售额"],
        table_id="fact_order",
    )
    repository = MetaMySQLRepository(session)

    column_info = await repository.get_column_info_by_id("fact_order.order_amount")

    assert column_info == ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0],
        description="订单金额。",
        alias=["销售额"],
        table_id="fact_order",
    )
    session.get.assert_awaited_once_with(
        ColumnInfoMySQL,
        "fact_order.order_amount",
    )


async def test_get_column_info_by_id_returns_none() -> None:
    """字段不存在时返回 None。"""

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    repository = MetaMySQLRepository(session)

    column_info = await repository.get_column_info_by_id("missing.column")

    assert column_info is None
    session.get.assert_awaited_once_with(ColumnInfoMySQL, "missing.column")


async def test_get_table_info_by_id() -> None:
    """查询表 ORM 后会转换成 TableInfo。"""

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = TableInfoMySQL(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )
    repository = MetaMySQLRepository(session)

    table_info = await repository.get_table_info_by_id("fact_order")

    assert table_info == TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )
    session.get.assert_awaited_once_with(TableInfoMySQL, "fact_order")


async def test_get_table_info_by_id_returns_none() -> None:
    """表不存在时返回 None。"""

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None
    repository = MetaMySQLRepository(session)

    table_info = await repository.get_table_info_by_id("missing_table")

    assert table_info is None
    session.get.assert_awaited_once_with(TableInfoMySQL, "missing_table")


async def test_get_key_columns_by_table_id() -> None:
    """主外键查询结果会转换成 ColumnInfo 列表。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.mappings.return_value.fetchall.return_value = [
        {
            "id": "fact_order.order_id",
            "name": "order_id",
            "type": "varchar(64)",
            "role": "primary_key",
            "examples": ["O001"],
            "description": "订单唯一标识。",
            "alias": ["订单ID"],
            "table_id": "fact_order",
        },
        {
            "id": "fact_order.region_id",
            "name": "region_id",
            "type": "varchar(64)",
            "role": "foreign_key",
            "examples": ["R001"],
            "description": "地区外键。",
            "alias": ["地区ID"],
            "table_id": "fact_order",
        },
    ]
    session.execute.return_value = result
    repository = MetaMySQLRepository(session)

    columns = await repository.get_key_columns_by_table_id("fact_order")

    assert columns == [
        ColumnInfo(
            id="fact_order.order_id",
            name="order_id",
            type="varchar(64)",
            role="primary_key",
            examples=["O001"],
            description="订单唯一标识。",
            alias=["订单ID"],
            table_id="fact_order",
        ),
        ColumnInfo(
            id="fact_order.region_id",
            name="region_id",
            type="varchar(64)",
            role="foreign_key",
            examples=["R001"],
            description="地区外键。",
            alias=["地区ID"],
            table_id="fact_order",
        ),
    ]
    statement = session.execute.await_args.args[0]
    parameters = session.execute.await_args.args[1]
    assert str(statement) == (
        "select * from column_info where table_id = :table_id "
        "and role in ('primary_key','foreign_key')"
    )
    assert parameters == {"table_id": "fact_order"}


async def test_get_key_columns_returns_empty_list() -> None:
    """指定表没有主外键时返回空列表。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.mappings.return_value.fetchall.return_value = []
    session.execute.return_value = result
    repository = MetaMySQLRepository(session)

    columns = await repository.get_key_columns_by_table_id("dim_unknown")

    assert columns == []
