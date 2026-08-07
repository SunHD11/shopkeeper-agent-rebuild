"""测试基于完整问数上下文生成候选 SQL 的节点。"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.generate_sql as generate_sql_module
from app.agent.state import DataAgentState


def create_text_llm(text: str) -> RunnableLambda:
    """创建返回固定纯文本的 LangChain Runnable。"""

    return RunnableLambda(lambda _: AIMessage(content=text))


def create_state() -> DataAgentState:
    """构造 SQL 生成节点所需的最小完整 State。"""

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
    )


async def test_generate_sql_serializes_context_and_returns_trimmed_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五类上下文正确进入 Prompt，模型输出去除首尾空白后写回 sql。"""

    mock_load_prompt = Mock(
        return_value=(
            "TABLE={table_infos}\nMETRIC={metric_infos}\nDATE={date_info}\n"
            "DB={db_info}\nQUERY={query}"
        )
    )
    monkeypatch.setattr(generate_sql_module, "load_prompt", mock_load_prompt)

    mock_yaml_dump = Mock(
        side_effect=["TABLE_YAML", "METRIC_YAML", "DATE_YAML", "DB_YAML"]
    )
    monkeypatch.setattr(generate_sql_module.yaml, "dump", mock_yaml_dump)

    received_prompts: list[str] = []

    def fake_llm(prompt_value: Any) -> AIMessage:
        received_prompts.append(prompt_value.to_string())
        return AIMessage(content="  SELECT SUM(order_amount) AS GMV FROM fact_order;\n")

    monkeypatch.setattr(generate_sql_module, "llm", RunnableLambda(fake_llm))

    state = create_state()
    writer = Mock()
    result = await generate_sql_module.generate_sql(
        state,
        SimpleNamespace(stream_writer=writer, context={}),
    )

    mock_load_prompt.assert_called_once_with("generate_sql")
    assert mock_yaml_dump.call_args_list == [
        call(state["table_infos"], allow_unicode=True, sort_keys=False),
        call(state["metric_infos"], allow_unicode=True, sort_keys=False),
        call(state["date_info"], allow_unicode=True, sort_keys=False),
        call(state["db_info"], allow_unicode=True, sort_keys=False),
    ]
    assert received_prompts == [
        "TABLE=TABLE_YAML\nMETRIC=METRIC_YAML\nDATE=DATE_YAML\n"
        "DB=DB_YAML\nQUERY=查询华东地区的销售总额"
    ]
    assert result == {"sql": "SELECT SUM(order_amount) AS GMV FROM fact_order;"}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "生成SQL", "status": "running"}),
        call({"type": "progress", "step": "生成SQL", "status": "success"}),
    ]


async def test_generate_sql_rejects_empty_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型只返回空白时不能继续进入数据库校验。"""

    monkeypatch.setattr(generate_sql_module, "llm", create_text_llm("  \n"))
    writer = Mock()

    with pytest.raises(ValueError, match="SQL 生成模型返回了空内容"):
        await generate_sql_module.generate_sql(
            create_state(),
            SimpleNamespace(stream_writer=writer, context={}),
        )

    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "生成SQL", "status": "error"}
    )


async def test_generate_sql_reports_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用失败时发送 error，并继续抛出原异常。"""

    async def failing_llm(_: Any) -> AIMessage:
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(generate_sql_module, "llm", RunnableLambda(failing_llm))
    writer = Mock()

    with pytest.raises(RuntimeError, match="llm unavailable"):
        await generate_sql_module.generate_sql(
            create_state(),
            SimpleNamespace(stream_writer=writer, context={}),
        )

    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "生成SQL", "status": "error"}
    )
