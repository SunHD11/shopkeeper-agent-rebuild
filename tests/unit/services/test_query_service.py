"""测试 QueryService 对 LangGraph 事件流和 SSE 的编排。"""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.services.query_service as query_service_module
from app.services.query_service import QueryService, format_sse_event


def create_service() -> tuple[QueryService, dict[str, Mock]]:
    """使用独立 Mock 构造 QueryService，并保留依赖便于身份断言。"""

    dependencies = {
        "meta_mysql_repository": Mock(name="meta_mysql_repository"),
        "embedding_client": Mock(name="embedding_client"),
        "dw_mysql_repository": Mock(name="dw_mysql_repository"),
        "column_qdrant_repository": Mock(name="column_qdrant_repository"),
        "metric_qdrant_repository": Mock(name="metric_qdrant_repository"),
        "value_es_repository": Mock(name="value_es_repository"),
    }
    return QueryService(**dependencies), dependencies


def decode_sse_event(message: str) -> dict:
    """从测试收到的单条 SSE 文本中取出 JSON 事件。"""

    assert message.startswith("data: ")
    assert message.endswith("\n\n")
    return json.loads(message.removeprefix("data: ").strip())


def test_format_sse_event_preserves_chinese_and_serializes_special_values() -> None:
    """中文保持可读，Decimal 和 date 通过 default=str 安全进入 JSON。"""

    message = format_sse_event(
        {
            "type": "result",
            "data": {
                "指标": "销售额",
                "value": Decimal("125000.50"),
                "date": date(2026, 8, 7),
            },
        }
    )

    assert "销售额" in message
    assert decode_sse_event(message) == {
        "type": "result",
        "data": {
            "指标": "销售额",
            "value": "125000.50",
            "date": "2026-08-07",
        },
    }


async def test_query_streams_graph_events_with_state_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用户问题进入初始 State，六个外部依赖原样进入 Runtime Context。"""

    captured: dict = {}

    async def fake_astream(*, input, context, stream_mode):
        captured.update(
            input=input,
            context=context,
            stream_mode=stream_mode,
        )
        yield {"type": "progress", "step": "抽取关键词", "status": "running"}
        yield {"type": "result", "data": [{"GMV": 125000.5}]}

    monkeypatch.setattr(
        query_service_module,
        "graph",
        SimpleNamespace(astream=fake_astream),
    )

    service, dependencies = create_service()
    messages = [message async for message in service.query("  查询华东销售额  ")]

    assert captured["input"] == {"query": "查询华东销售额"}
    assert captured["stream_mode"] == "custom"
    context = captured["context"]
    assert context["meta_mysql_repository"] is dependencies["meta_mysql_repository"]
    assert context["embedding_client"] is dependencies["embedding_client"]
    assert context["dw_mysql_repository"] is dependencies["dw_mysql_repository"]
    assert (
        context["column_qdrant_repository"] is dependencies["column_qdrant_repository"]
    )
    assert (
        context["metric_qdrant_repository"] is dependencies["metric_qdrant_repository"]
    )
    assert context["value_es_repository"] is dependencies["value_es_repository"]

    assert [decode_sse_event(message) for message in messages] == [
        {"type": "progress", "step": "抽取关键词", "status": "running"},
        {"type": "result", "data": [{"GMV": 125000.5}]},
    ]


async def test_query_converts_graph_error_to_final_sse_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流已经开始后 Graph 失败，Service 仍追加标准 error 事件。"""

    async def failing_astream(**_):
        yield {"type": "progress", "step": "生成SQL", "status": "running"}
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(
        query_service_module,
        "graph",
        SimpleNamespace(astream=failing_astream),
    )

    service, _ = create_service()
    messages = [message async for message in service.query("查询销售额")]

    assert [decode_sse_event(message) for message in messages] == [
        {"type": "progress", "step": "生成SQL", "status": "running"},
        {"type": "error", "message": "llm unavailable"},
    ]


async def test_query_rejects_blank_question_without_starting_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """纯空白问题直接形成 SSE error，不启动 LangGraph。"""

    graph = Mock()
    monkeypatch.setattr(query_service_module, "graph", graph)

    service, _ = create_service()
    messages = [message async for message in service.query(" \n ")]

    assert [decode_sse_event(message) for message in messages] == [
        {"type": "error", "message": "用户问题不能为空"}
    ]
    graph.astream.assert_not_called()
