"""测试在线 Agent 的指标向量召回节点。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.recall_metric as recall_metric_module
from app.agent.state import DataAgentState
from app.entities.metric_info import MetricInfo


def create_json_llm(values: list[str]) -> RunnableLambda:
    """创建不会访问真实模型的 JSON 响应 Runnable。"""

    return RunnableLambda(
        lambda _: AIMessage(
            content=json.dumps(values, ensure_ascii=False),
        )
    )


async def test_recall_metric_expands_searches_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """指标扩展词参与向量检索，重复命中的指标按业务 id 去重。"""

    state = DataAgentState(
        query="查询华东地区的销售总额",
        keywords=["华东", "销售总额"],
    )
    writer = Mock()

    gmv = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有有效订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )

    embedding_client = Mock()
    embedding_client.aembed_query = AsyncMock(return_value=[0.3, 0.4])
    metric_repository = Mock()
    metric_repository.search = AsyncMock(return_value=[gmv])
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={
            "embedding_client": embedding_client,
            "metric_qdrant_repository": metric_repository,
        },
    )

    mock_load_prompt = Mock(return_value="用户问题：{query}\n仅输出 JSON 数组。")
    monkeypatch.setattr(recall_metric_module, "load_prompt", mock_load_prompt)
    monkeypatch.setattr(
        recall_metric_module,
        "llm",
        create_json_llm(["GMV", "成交总额"]),
    )

    result = await recall_metric_module.recall_metric(state, runtime)

    expected_keywords = {"华东", "销售总额", "GMV", "成交总额"}
    actual_keywords = {
        current_call.args[0]
        for current_call in embedding_client.aembed_query.await_args_list
    }

    mock_load_prompt.assert_called_once_with("extend_keywords_for_metric_recall")
    assert actual_keywords == expected_keywords
    assert metric_repository.search.await_count == len(expected_keywords)
    assert all(
        current_call.args == ([0.3, 0.4],)
        for current_call in metric_repository.search.await_args_list
    )
    assert result == {"retrieved_metric_infos": [gmv]}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回指标信息", "status": "running"}),
        call({"type": "progress", "step": "召回指标信息", "status": "success"}),
    ]


async def test_recall_metric_reports_qdrant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """指标 Qdrant 查询失败时发送 error，并重新抛出异常。"""

    writer = Mock()
    embedding_client = Mock()
    embedding_client.aembed_query = AsyncMock(return_value=[0.3, 0.4])
    metric_repository = Mock()
    metric_repository.search = AsyncMock(side_effect=RuntimeError("qdrant unavailable"))
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={
            "embedding_client": embedding_client,
            "metric_qdrant_repository": metric_repository,
        },
    )

    monkeypatch.setattr(
        recall_metric_module,
        "llm",
        create_json_llm(["GMV"]),
    )

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        await recall_metric_module.recall_metric(
            DataAgentState(query="查询销售额", keywords=["销售额"]),
            runtime,
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回指标信息", "status": "running"}),
        call({"type": "progress", "step": "召回指标信息", "status": "error"}),
    ]
