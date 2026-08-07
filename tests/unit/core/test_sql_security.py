"""测试 LLM SQL 的应用层只读安全边界。"""

import pytest

from app.core.sql_security import UnsafeSQLError, validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fact_order",
        "WITH totals AS (SELECT SUM(order_amount) AS value FROM fact_order) "
        "SELECT value FROM totals",
        "SELECT 'delete is only text' AS message",
        "/* read only */ SELECT 1;",
    ],
)
def test_validate_read_only_sql_accepts_queries(sql: str) -> None:
    assert validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DELETE FROM fact_order",
        "UPDATE fact_order SET order_amount = 0",
        "SELECT 1; DROP TABLE fact_order",
        "WITH changed AS (DELETE FROM fact_order RETURNING order_id) "
        "SELECT * FROM changed",
        "SELECT * FROM fact_order FOR UPDATE",
        "SELECT * FROM fact_order INTO OUTFILE '/tmp/orders.csv'",
    ],
)
def test_validate_read_only_sql_rejects_unsafe_statements(sql: str) -> None:
    with pytest.raises(UnsafeSQLError):
        validate_read_only_sql(sql)
