"""测试执行最终 SQL 并流式返回查询结果的节点。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.agent.nodes.run_sql import run_sql
from app.agent.state import DataAgentState


def create_runtime(repository: Mock, writer: Mock) -> SimpleNamespace:
    """构造最终 SQL 执行节点所需的 Runtime 替身。"""

    return SimpleNamespace(
        stream_writer=writer,
        context={"dw_mysql_repository": repository},
    )


async def test_run_sql_executes_query_and_streams_result() -> None:
    """Repository 返回的普通字典列表通过 result 事件原样输出。"""

    sql = "SELECT region_name, SUM(order_amount) AS GMV FROM fact_order"
    rows = [
        {"region_name": "华东", "GMV": 125000.5},
        {"region_name": "华南", "GMV": 98000.0},
    ]
    repository = Mock()
    repository.run = AsyncMock(return_value=rows)
    writer = Mock()

    result = await run_sql(
        DataAgentState(sql=sql),
        create_runtime(repository, writer),
    )

    repository.run.assert_awaited_once_with(sql)
    assert result is None
    assert writer.call_args_list == [
        call({"type": "progress", "step": "执行SQL", "status": "running"}),
        call({"type": "progress", "step": "执行SQL", "status": "success"}),
        call({"type": "result", "data": rows}),
    ]


async def test_run_sql_reports_repository_error_without_result_event() -> None:
    """查询失败时只发送 error，不得再伪造 success 或结果事件。"""

    repository = Mock()
    repository.run = AsyncMock(side_effect=RuntimeError("query failed"))
    writer = Mock()

    with pytest.raises(RuntimeError, match="query failed"):
        await run_sql(
            DataAgentState(sql="SELECT * FROM fact_order"),
            create_runtime(repository, writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "执行SQL", "status": "running"}),
        call({"type": "progress", "step": "执行SQL", "status": "error"}),
    ]


async def test_run_sql_rejects_empty_sql_before_repository_call() -> None:
    """空 SQL 在访问 DW 前立即失败。"""

    repository = Mock()
    repository.run = AsyncMock()
    writer = Mock()

    with pytest.raises(ValueError, match="待执行 SQL 不能为空"):
        await run_sql(
            DataAgentState(sql="\n "),
            create_runtime(repository, writer),
        )

    repository.run.assert_not_awaited()
    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "执行SQL", "status": "error"}
    )
