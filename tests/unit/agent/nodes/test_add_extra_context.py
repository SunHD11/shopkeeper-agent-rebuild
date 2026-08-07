"""测试 SQL 生成前的日期与数据库环境补全节点。"""

from datetime import date as real_date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

import app.agent.nodes.add_extra_context as add_extra_context_module
from app.agent.state import DataAgentState


def create_runtime(repository: Mock, writer: Mock) -> SimpleNamespace:
    """构造只包含 DW Repository 和 stream_writer 的 Runtime 替身。"""

    return SimpleNamespace(
        stream_writer=writer,
        context={"dw_mysql_repository": repository},
    )


async def test_add_extra_context_builds_date_and_database_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定系统日期并验证日期、季度和真实数据库环境都写入 State。"""

    class FixedDate(real_date):
        """替代模块内的 date.today()，让测试不依赖运行当天。"""

        @classmethod
        def today(cls) -> "FixedDate":
            return cls(2026, 8, 7)

    monkeypatch.setattr(add_extra_context_module, "date", FixedDate)

    repository = Mock()
    repository.get_db_info = AsyncMock(
        return_value={"dialect": "mysql", "version": "8.4.6"}
    )
    writer = Mock()

    result = await add_extra_context_module.add_extra_context(
        DataAgentState(query="查询本季度销售额"),
        create_runtime(repository, writer),
    )

    repository.get_db_info.assert_awaited_once_with()
    assert result == {
        "date_info": {
            "date": "2026-08-07",
            "weekday": "Friday",
            "quarter": "Q3",
        },
        "db_info": {
            "dialect": "mysql",
            "version": "8.4.6",
        },
    }
    assert writer.call_args_list == [
        call({"type": "progress", "step": "添加额外上下文", "status": "running"}),
        call({"type": "progress", "step": "添加额外上下文", "status": "success"}),
    ]


@pytest.mark.parametrize(
    ("database_info", "expected_message"),
    [
        ({"dialect": "", "version": "8.4.6"}, "数据库方言"),
        ({"dialect": "mysql", "version": None}, "数据库版本"),
    ],
    ids=["missing-dialect", "missing-version"],
)
async def test_add_extra_context_rejects_incomplete_database_info(
    database_info: dict[str, str | None],
    expected_message: str,
) -> None:
    """数据库环境不完整时报告 error，不能把不可信信息交给 SQL 模型。"""

    repository = Mock()
    repository.get_db_info = AsyncMock(return_value=database_info)
    writer = Mock()

    with pytest.raises(ValueError, match=expected_message):
        await add_extra_context_module.add_extra_context(
            DataAgentState(query="查询销售额"),
            create_runtime(repository, writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "添加额外上下文", "status": "running"}),
        call({"type": "progress", "step": "添加额外上下文", "status": "error"}),
    ]


async def test_add_extra_context_reports_repository_error() -> None:
    """DW 环境查询失败时保留原异常，并发送 error 事件。"""

    repository = Mock()
    repository.get_db_info = AsyncMock(side_effect=RuntimeError("dw unavailable"))
    writer = Mock()

    with pytest.raises(RuntimeError, match="dw unavailable"):
        await add_extra_context_module.add_extra_context(
            DataAgentState(query="查询销售额"),
            create_runtime(repository, writer),
        )

    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "添加额外上下文", "status": "error"}
    )
