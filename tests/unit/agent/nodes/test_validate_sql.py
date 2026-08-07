"""测试使用真实 DW Repository 语义校验候选 SQL 的节点。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataAgentState


def create_runtime(repository: Mock, writer: Mock) -> SimpleNamespace:
    """构造 SQL 校验节点所需的 Runtime 替身。"""

    return SimpleNamespace(
        stream_writer=writer,
        context={"dw_mysql_repository": repository},
    )


async def test_validate_sql_returns_none_when_explain_succeeds() -> None:
    """DW EXPLAIN 成功时清空 error，Graph 后续应直接进入 run_sql。"""

    repository = Mock()
    repository.validate = AsyncMock(return_value=None)
    writer = Mock()
    sql = "SELECT SUM(order_amount) AS GMV FROM fact_order"

    result = await validate_sql(
        DataAgentState(sql=sql),
        create_runtime(repository, writer),
    )

    repository.validate.assert_awaited_once_with(sql)
    assert result == {"error": None}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "校验SQL", "status": "running"}),
        call({"type": "progress", "step": "校验SQL", "status": "success"}),
    ]


async def test_validate_sql_returns_database_error_for_correction() -> None:
    """数据库拒绝 SQL 时不终止 Graph，而是把错误文本写入条件分支 State。"""

    repository = Mock()
    repository.validate = AsyncMock(
        side_effect=RuntimeError("Unknown column 'order_total'")
    )
    writer = Mock()

    result = await validate_sql(
        DataAgentState(sql="SELECT order_total FROM fact_order"),
        create_runtime(repository, writer),
    )

    assert result == {"error": "Unknown column 'order_total'"}
    # “成功发现 SQL 错误”是校验节点的正常业务结果，所以进度仍是 success。
    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "校验SQL", "status": "success"}
    )


async def test_validate_sql_rejects_empty_sql_before_repository_call() -> None:
    """空 SQL 属于节点输入错误，应报告 error 而不是伪装成数据库校验失败。"""

    repository = Mock()
    repository.validate = AsyncMock()
    writer = Mock()

    with pytest.raises(ValueError, match="待校验 SQL 不能为空"):
        await validate_sql(
            DataAgentState(sql="  "),
            create_runtime(repository, writer),
        )

    repository.validate.assert_not_awaited()
    assert writer.call_args_list == [
        call({"type": "progress", "step": "校验SQL", "status": "running"}),
        call({"type": "progress", "step": "校验SQL", "status": "error"}),
    ]
