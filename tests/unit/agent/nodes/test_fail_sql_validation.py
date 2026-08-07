"""测试 SQL 自动修正失败后的终止节点。"""

from unittest.mock import Mock

import pytest

from app.agent.nodes.fail_sql_validation import fail_sql_validation
from app.agent.state import DataAgentState


async def test_fail_sql_validation_reports_error_and_raises() -> None:
    writer = Mock()
    runtime = Mock(stream_writer=writer)
    state = DataAgentState(error="Unknown column 'missing_column'")

    with pytest.raises(ValueError, match="自动修正一次后仍未通过校验"):
        await fail_sql_validation(state, runtime)

    writer.assert_called_once_with(
        {
            "type": "progress",
            "step": "终止SQL执行",
            "status": "error",
        }
    )
