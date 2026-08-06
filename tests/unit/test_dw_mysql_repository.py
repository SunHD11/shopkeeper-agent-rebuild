"""测试 DW MySQL Repository 的 SQL 生成和结果转换。"""

from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


async def test_get_column_types() -> None:
    """SHOW COLUMNS 结果会转换成字段名到字段类型的字典。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.mappings.return_value.fetchall.return_value = [
        {"Field": "order_id", "Type": "varchar(64)"},
        {"Field": "order_amount", "Type": "decimal(10,2)"},
    ]
    session.execute.return_value = result
    repository = DWMySQLRepository(session)

    column_types = await repository.get_column_types("fact_order")

    assert column_types == {
        "order_id": "varchar(64)",
        "order_amount": "decimal(10,2)",
    }
    statement = session.execute.await_args.args[0]
    assert str(statement) == "show columns from fact_order"


async def test_get_column_values() -> None:
    """单列查询结果会转换成不带行包装的字段值列表。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.fetchall.return_value = [("华东",), ("华南",), ("华北",)]
    session.execute.return_value = result
    repository = DWMySQLRepository(session)

    values = await repository.get_column_values(
        table_name="dim_region",
        column_name="region_name",
        limit=10,
    )

    assert values == ["华东", "华南", "华北"]
    statement = session.execute.await_args.args[0]
    assert str(statement) == ("select distinct region_name from dim_region limit 10")


async def test_get_column_values_returns_empty_list() -> None:
    """字段没有数据时返回空列表。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.fetchall.return_value = []
    session.execute.return_value = result
    repository = DWMySQLRepository(session)

    values = await repository.get_column_values(
        table_name="dim_region",
        column_name="region_name",
    )

    assert values == []


async def test_get_db_info() -> None:
    """数据库版本和 Session 所绑定的方言会组成环境信息。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.scalar.return_value = "8.4.6"
    session.execute.return_value = result
    session.bind = Mock()
    session.bind.dialect.name = "mysql"
    repository = DWMySQLRepository(session)

    db_info = await repository.get_db_info()

    assert db_info == {
        "dialect": "mysql",
        "version": "8.4.6",
    }
    statement = session.execute.await_args.args[0]
    assert str(statement) == "select version()"


async def test_validate_uses_explain() -> None:
    """校验 SQL 时会在原始查询前添加 EXPLAIN。"""

    session = AsyncMock(spec=AsyncSession)
    repository = DWMySQLRepository(session)

    result = await repository.validate("select * from fact_order")

    assert result is None
    statement = session.execute.await_args.args[0]
    assert str(statement) == "explain select * from fact_order"


async def test_run_returns_dictionary_rows() -> None:
    """最终查询结果会转换成普通字典列表。"""

    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.mappings.return_value.fetchall.return_value = [
        {"region_name": "华东", "gmv": 10000},
        {"region_name": "华南", "gmv": 8000},
    ]
    session.execute.return_value = result
    repository = DWMySQLRepository(session)

    rows = await repository.run("select region_name, gmv from result")

    assert rows == [
        {"region_name": "华东", "gmv": 10000},
        {"region_name": "华南", "gmv": 8000},
    ]
    statement = session.execute.await_args.args[0]
    assert str(statement) == "select region_name, gmv from result"
