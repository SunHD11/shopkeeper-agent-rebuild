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


async def test_save_table_infos() -> None:
    """表实体会转换成 TableInfoMySQL 并通过 merge 幂等保存。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    table_info = TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )

    await repository.save_table_infos([table_info])

    model = session.merge.await_args.args[0]
    assert isinstance(model, TableInfoMySQL)
    assert model.id == "fact_order"
    assert model.name == "fact_order"
    assert model.role == "fact"
    assert model.description == "订单事实表。"


async def test_save_column_infos() -> None:
    """字段实体会转换成 ColumnInfoMySQL 并通过 merge 幂等保存。"""

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

    await repository.save_column_infos([column_info])

    model = session.merge.await_args.args[0]
    assert isinstance(model, ColumnInfoMySQL)
    assert model.id == "fact_order.order_amount"
    assert model.type == "decimal(10,2)"
    assert model.examples == [100.0, 268.0]
    assert model.alias == ["销售额", "收入"]
    assert model.table_id == "fact_order"


async def test_save_metric_infos() -> None:
    """指标实体会转换成 MetricInfoMySQL 并通过 merge 幂等保存。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    metric_info = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    await repository.save_metric_infos([metric_info])

    model = session.merge.await_args.args[0]
    assert isinstance(model, MetricInfoMySQL)
    assert model.id == "GMV"
    assert model.description == "所有订单的成交金额总和。"
    assert model.relevant_columns == ["fact_order.order_amount"]
    assert model.alias == ["成交总额", "订单总额"]


async def test_save_column_metrics() -> None:
    """字段指标关系会转换成 ColumnMetricMySQL 并通过 merge 幂等保存。"""

    session = AsyncMock(spec=AsyncSession)
    repository = MetaMySQLRepository(session)
    relationship = ColumnMetric(
        column_id="fact_order.order_amount",
        metric_id="GMV",
    )

    await repository.save_column_metrics([relationship])

    model = session.merge.await_args.args[0]
    assert isinstance(model, ColumnMetricMySQL)
    assert model.column_id == "fact_order.order_amount"
    assert model.metric_id == "GMV"


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
