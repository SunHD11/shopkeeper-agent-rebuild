"""测试在线 Agent 的公共关键词抽取节点。"""

from types import SimpleNamespace
from unittest.mock import Mock

import jieba.analyse
import pytest

from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.state import DataAgentState


def create_runtime(writer: Mock) -> SimpleNamespace:
    """创建只提供 stream_writer 的轻量 Runtime 替身。"""

    # extract_keywords 不读取 runtime.context，因此无需构造六个真实依赖。
    # SimpleNamespace 足以表达本节点真正使用的 Runtime 接口。
    return SimpleNamespace(stream_writer=writer)


async def test_extract_keywords_returns_jieba_terms_and_full_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """节点应保留 Jieba 关键词，并把完整原问题作为召回兜底。"""

    query = "查询华东地区最近三个月的销售总额"
    state = DataAgentState(query=query)
    writer = Mock()
    runtime = create_runtime(writer)

    # Mock Jieba 可以让测试不依赖词典版本和 TF-IDF 权重，
    # 只验证节点如何使用抽取结果。
    mock_extract_tags = Mock(return_value=["华东", "销售总额"])
    monkeypatch.setattr(jieba.analyse, "extract_tags", mock_extract_tags)

    result = await extract_keywords(state, runtime)

    # 原项目使用 set 去重，结果顺序不稳定，所以使用集合比较。
    assert set(result["keywords"]) == {"华东", "销售总额", query}

    mock_extract_tags.assert_called_once()
    call = mock_extract_tags.call_args
    assert call.args == (query,)
    assert set(call.kwargs["allowPOS"]) == {
        "n",
        "nr",
        "ns",
        "nt",
        "nz",
        "v",
        "vn",
        "a",
        "an",
        "eng",
        "i",
        "l",
    }

    # 成功链路必须按 running -> success 的顺序发送进度。
    assert writer.call_args_list == [
        (({"type": "progress", "step": "抽取关键词", "status": "running"},), {}),
        (({"type": "progress", "step": "抽取关键词", "status": "success"},), {}),
    ]


async def test_extract_keywords_removes_duplicates_and_keeps_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重复关键词只保留一次，即使 Jieba 没有结果也不能丢失原问题。"""

    query = "查询销售总额"
    writer = Mock()
    runtime = create_runtime(writer)

    # 模拟 Jieba 重复返回相同词，并且已经包含完整问题。
    monkeypatch.setattr(
        jieba.analyse,
        "extract_tags",
        Mock(return_value=["销售总额", "销售总额", query]),
    )

    result = await extract_keywords(DataAgentState(query=query), runtime)

    assert set(result["keywords"]) == {"销售总额", query}
    assert len(result["keywords"]) == 2


async def test_extract_keywords_reports_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Jieba 抽取失败时应发送 error 进度，并把原异常继续抛出。"""

    query = "查询销售总额"
    writer = Mock()
    runtime = create_runtime(writer)
    error = RuntimeError("jieba failed")

    monkeypatch.setattr(
        jieba.analyse,
        "extract_tags",
        Mock(side_effect=error),
    )

    with pytest.raises(RuntimeError, match="jieba failed"):
        await extract_keywords(DataAgentState(query=query), runtime)

    # 失败路径不能发送 success，也不能吞掉异常返回空关键词。
    assert writer.call_args_list == [
        (({"type": "progress", "step": "抽取关键词", "status": "running"},), {}),
        (({"type": "progress", "step": "抽取关键词", "status": "error"},), {}),
    ]
