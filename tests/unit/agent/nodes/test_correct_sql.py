"""测试根据数据库错误修正候选 SQL 的节点。"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.correct_sql as correct_sql_module
from app.agent.state import DataAgentState


def create_text_llm(text: str) -> RunnableLambda:
    """创建返回固定 SQL 文本的 LangChain Runnable。"""

    return RunnableLambda(lambda _: AIMessage(content=text))


def create_state(error: str | None = "Unknown column 'order_total'") -> DataAgentState:
    """构造 SQL 修正节点需要的完整上下文。"""

    return DataAgentState(
        query="查询华东地区的销售总额",
        table_infos=[
            {
                "name": "fact_order",
                "role": "fact",
                "description": "订单事实表。",
                "columns": [],
            }
        ],
        metric_infos=[
            {
                "name": "GMV",
                "description": "已支付订单的成交总额。",
                "relevant_columns": ["fact_order.order_amount"],
                "alias": ["销售总额"],
            }
        ],
        date_info={"date": "2026-08-07", "weekday": "Friday", "quarter": "Q3"},
        db_info={"dialect": "mysql", "version": "8.4.6"},
        sql="SELECT SUM(order_total) AS GMV FROM fact_order",
        error=error,
    )


async def test_correct_sql_passes_error_and_context_and_returns_trimmed_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原问题、原 SQL、数据库错误和四类上下文都进入修正 Prompt。"""

    mock_load_prompt = Mock(
        return_value=(
            "TABLE={table_infos}\nMETRIC={metric_infos}\nDATE={date_info}\n"
            "DB={db_info}\nQUERY={query}\nSQL={sql}\nERROR={error}"
        )
    )
    monkeypatch.setattr(correct_sql_module, "load_prompt", mock_load_prompt)

    mock_yaml_dump = Mock(
        side_effect=["TABLE_YAML", "METRIC_YAML", "DATE_YAML", "DB_YAML"]
    )
    monkeypatch.setattr(correct_sql_module.yaml, "dump", mock_yaml_dump)

    received_prompts: list[str] = []

    def fake_llm(prompt_value: Any) -> AIMessage:
        received_prompts.append(prompt_value.to_string())
        return AIMessage(content="  SELECT SUM(order_amount) AS GMV FROM fact_order;\n")

    monkeypatch.setattr(correct_sql_module, "llm", RunnableLambda(fake_llm))

    state = create_state()
    writer = Mock()
    result = await correct_sql_module.correct_sql(
        state,
        SimpleNamespace(stream_writer=writer, context={}),
    )

    mock_load_prompt.assert_called_once_with("correct_sql")
    assert mock_yaml_dump.call_args_list == [
        call(state["table_infos"], allow_unicode=True, sort_keys=False),
        call(state["metric_infos"], allow_unicode=True, sort_keys=False),
        call(state["date_info"], allow_unicode=True, sort_keys=False),
        call(state["db_info"], allow_unicode=True, sort_keys=False),
    ]
    assert received_prompts == [
        "TABLE=TABLE_YAML\nMETRIC=METRIC_YAML\nDATE=DATE_YAML\nDB=DB_YAML\n"
        "QUERY=查询华东地区的销售总额\n"
        "SQL=SELECT SUM(order_total) AS GMV FROM fact_order\n"
        "ERROR=Unknown column 'order_total'"
    ]
    assert result == {
        "sql": "SELECT SUM(order_amount) AS GMV FROM fact_order;",
        "sql_correction_attempts": 1,
    }
    assert writer.call_args_list == [
        call({"type": "progress", "step": "校正SQL", "status": "running"}),
        call({"type": "progress", "step": "校正SQL", "status": "success"}),
    ]


@pytest.mark.parametrize("error", [None, "  "], ids=["none", "blank"])
async def test_correct_sql_requires_validation_error(error: str | None) -> None:
    """没有数据库校验错误时不允许误入 SQL 修正节点。"""

    writer = Mock()

    with pytest.raises(ValueError, match="需要非空的数据库校验错误"):
        await correct_sql_module.correct_sql(
            create_state(error),
            SimpleNamespace(stream_writer=writer, context={}),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "校正SQL", "status": "running"}),
        call({"type": "progress", "step": "校正SQL", "status": "error"}),
    ]


async def test_correct_sql_rejects_empty_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """修正模型返回空白时不允许覆盖原 SQL。"""

    monkeypatch.setattr(correct_sql_module, "llm", create_text_llm(" \n "))
    writer = Mock()

    with pytest.raises(ValueError, match="SQL 修正模型返回了空内容"):
        await correct_sql_module.correct_sql(
            create_state(),
            SimpleNamespace(stream_writer=writer, context={}),
        )

    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "校正SQL", "status": "error"}
    )


async def test_correct_sql_reports_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用异常时保留原始错误并发送 error 进度。"""

    async def failing_llm(_: Any) -> AIMessage:
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(correct_sql_module, "llm", RunnableLambda(failing_llm))
    writer = Mock()

    with pytest.raises(RuntimeError, match="llm unavailable"):
        await correct_sql_module.correct_sql(
            create_state(),
            SimpleNamespace(stream_writer=writer, context={}),
        )

    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "校正SQL", "status": "error"}
    )
