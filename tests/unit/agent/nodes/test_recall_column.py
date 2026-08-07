"""测试在线 Agent 的字段向量召回节点。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.recall_column as recall_column_module
from app.agent.state import DataAgentState
from app.entities.column_info import ColumnInfo


def create_json_llm(values: list[str]) -> RunnableLambda:
    """创建返回固定 JSON 数组的 LangChain Runnable。"""

    # PromptTemplate | llm | JsonOutputParser 仍会按真实 LCEL 管道运行；
    # 这里只替换远端模型调用，确保测试不访问网络也不消耗额度。
    return RunnableLambda(
        lambda _: AIMessage(
            content=json.dumps(values, ensure_ascii=False),
        )
    )


async def test_recall_column_expands_searches_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公共词和字段扩展词都参与检索，重复字段按 ColumnInfo.id 合并。"""

    query = "查询华东地区的销售总额"
    state = DataAgentState(
        query=query,
        keywords=["华东", "销售总额"],
    )
    writer = Mock()

    order_amount = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="float",
        role="measure",
        examples=[100.0],
        description="订单成交金额。",
        alias=["销售额"],
        table_id="fact_order",
    )

    embedding_client = Mock()
    embedding_client.aembed_query = AsyncMock(return_value=[0.1, 0.2])
    column_repository = Mock()
    # 每个关键词都返回同一个字段，模拟字段名称、描述、别名被重复命中的情况。
    column_repository.search = AsyncMock(return_value=[order_amount])
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={
            "embedding_client": embedding_client,
            "column_qdrant_repository": column_repository,
        },
    )

    mock_load_prompt = Mock(return_value="用户问题：{query}\n仅输出 JSON 数组。")
    monkeypatch.setattr(recall_column_module, "load_prompt", mock_load_prompt)
    monkeypatch.setattr(
        recall_column_module,
        "llm",
        create_json_llm(["地区", "订单金额"]),
    )

    result = await recall_column_module.recall_column(state, runtime)

    expected_keywords = {"华东", "销售总额", "地区", "订单金额"}
    actual_keywords = {
        current_call.args[0]
        for current_call in embedding_client.aembed_query.await_args_list
    }

    mock_load_prompt.assert_called_once_with("extend_keywords_for_column_recall")
    assert actual_keywords == expected_keywords
    assert embedding_client.aembed_query.await_count == len(expected_keywords)
    assert column_repository.search.await_count == len(expected_keywords)
    assert all(
        current_call.args == ([0.1, 0.2],)
        for current_call in column_repository.search.await_args_list
    )

    # 即使四个关键词都命中同一个字段，State 中也只能保留一个业务实体。
    assert result == {"retrieved_column_infos": [order_amount]}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回字段信息", "status": "running"}),
        call({"type": "progress", "step": "召回字段信息", "status": "success"}),
    ]


async def test_recall_column_reports_embedding_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding 失败时发送 error，并把原异常继续抛给 LangGraph。"""

    writer = Mock()
    embedding_client = Mock()
    embedding_client.aembed_query = AsyncMock(
        side_effect=RuntimeError("embedding unavailable")
    )
    column_repository = Mock()
    column_repository.search = AsyncMock()
    runtime = SimpleNamespace(
        stream_writer=writer,
        context={
            "embedding_client": embedding_client,
            "column_qdrant_repository": column_repository,
        },
    )

    monkeypatch.setattr(
        recall_column_module,
        "llm",
        create_json_llm(["订单金额"]),
    )

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await recall_column_module.recall_column(
            DataAgentState(query="查询销售额", keywords=["销售额"]),
            runtime,
        )

    column_repository.search.assert_not_awaited()
    assert writer.call_args_list == [
        call({"type": "progress", "step": "召回字段信息", "status": "running"}),
        call({"type": "progress", "step": "召回字段信息", "status": "error"}),
    ]
