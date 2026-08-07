"""使用真实 DW MySQL 验证只读校验和结果行数边界。"""

import pytest

from app.clients.mysql_client_manager import dw_mysql_client_manager
from app.core.sql_security import UnsafeSQLError
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

pytestmark = pytest.mark.integration


async def test_real_dw_repository_accepts_select_and_rejects_delete() -> None:
    dw_mysql_client_manager.init()

    try:
        session_factory = dw_mysql_client_manager.require_session_factory()
        async with session_factory() as session:
            repository = DWMySQLRepository(session)

            await repository.validate("SELECT SUM(order_amount) AS GMV FROM fact_order")
            rows = await repository.run(
                "SELECT SUM(order_amount) AS GMV FROM fact_order"
            )

            assert len(rows) == 1
            assert rows[0]["GMV"] > 0

            with pytest.raises(UnsafeSQLError):
                await repository.run("DELETE FROM fact_order")
    finally:
        await dw_mysql_client_manager.close()
