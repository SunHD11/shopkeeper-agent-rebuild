"""测试在线 Agent 的字段真实值 Elasticsearch 召回节点。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.recall_value as recall_value_module
from app.agent.state import DataAgentState
from app.entities.value_info import ValueInfo


def create_json_llm(values: list[str]) -> RunnableLambda:
    """创建返回固定字段值候选的本地 LangChain Runnable。"""

    return RunnableLambda(
        lambda _: AIMessage(
            content=json.dumps(values, ensure_ascii=False),
        )
    )


async def test_recall_value_expands_searches_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """字段值扩展词进入 ES 检索，重复 ValueInfo 按业务 id 合并。"""

    state = DataAgentState(
        query="查询华东地区的销售总额",
        keywords=["华东", "销售总额"],
    )
    writer = Mock()

    east_china = ValueInfo(
        id="dim_region.region_name.华东",
        value="华东",
        column_id="dim_region.region_name",
    )

    value_repository = Mock()
    value_repository.search = AsyncMock(return_value=[east_china])
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={"value_es_repository": value_repository},
    )

    mock_load_prompt = Mock(return_value="用户问题：{query}\n仅输出 JSON 数组。")
    monkeypatch.setattr(recall_value_module, "load_prompt", mock_load_prompt)
    monkeypatch.setattr(
        recall_value_module,
        "llm",
        create_json_llm(["华东", "华东地区"]),
    )

    result = await recall_value_module.recall_value(state, runtime)

    expected_keywords = {"华东", "销售总额", "华东地区"}
    actual_keywords = {
        current_call.args[0] for current_call in value_repository.search.await_args_list
    }

    mock_load_prompt.assert_called_once_with("extend_keywords_for_value_recall")
    assert actual_keywords == expected_keywords
    assert value_repository.search.await_count == len(expected_keywords)
    assert result == {"retrieved_value_infos": [east_china]}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回字段取值", "status": "running"}),
        call({"type": "progress", "step": "召回字段取值", "status": "success"}),
    ]


async def test_recall_value_reports_elasticsearch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Elasticsearch 查询失败时发送 error，并重新抛出异常。"""

    writer = Mock()
    value_repository = Mock()
    value_repository.search = AsyncMock(
        side_effect=RuntimeError("elasticsearch unavailable")
    )
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={"value_es_repository": value_repository},
    )

    monkeypatch.setattr(
        recall_value_module,
        "llm",
        create_json_llm(["华东"]),
    )

    with pytest.raises(RuntimeError, match="elasticsearch unavailable"):
        await recall_value_module.recall_value(
            DataAgentState(query="查询华东销售额", keywords=["华东"]),
            runtime,
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回字段取值", "status": "running"}),
        call({"type": "progress", "step": "召回字段取值", "status": "error"}),
    ]
