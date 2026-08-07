"""测试在线 Agent 的候选指标过滤节点。"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.filter_metric as filter_metric_module
from app.agent.state import DataAgentState, MetricInfoState


def create_json_llm(value: Any) -> RunnableLambda:
    """创建返回固定 JSON 内容的 LangChain Runnable。"""

    # 测试仍然执行真实的 PromptTemplate 和 JsonOutputParser，只替换远端 LLM。
    # 这样既不会访问网络，也可以验证 LCEL 管道和 JSON 解析是否正确衔接。
    return RunnableLambda(
        lambda _: AIMessage(
            content=json.dumps(value, ensure_ascii=False),
        )
    )


def create_metric_infos() -> list[MetricInfoState]:
    """构造一组同时包含金额、数量和平均值的候选指标。"""

    return [
        MetricInfoState(
            name="GMV",
            description="已支付订单的成交总额。",
            relevant_columns=[
                "fact_order.order_amount",
                "fact_order.order_status",
            ],
            alias=["销售总额", "成交总额"],
        ),
        MetricInfoState(
            name="订单数量",
            description="符合条件的订单总数量。",
            relevant_columns=["fact_order.order_id"],
            alias=["订单数"],
        ),
        MetricInfoState(
            name="客单价",
            description="平均每笔订单的成交金额。",
            relevant_columns=[
                "fact_order.order_amount",
                "fact_order.order_id",
            ],
            alias=["平均订单金额"],
        ),
    ]


def create_runtime(writer: Mock) -> SimpleNamespace:
    """创建只提供 stream_writer 的轻量 Runtime 替身。"""

    # filter_metric 不使用 DataAgentContext 中的 Repository 或客户端；
    # 它只读取 State、调用模块级 llm，并通过 stream_writer 报告进度。
    return SimpleNamespace(stream_writer=writer, context={})


async def test_filter_metric_selects_original_metric_structures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 只返回名称，程序从原候选中保留完整且可信的指标结构。"""

    metric_infos = create_metric_infos()
    writer = Mock()

    # 固定 Prompt 文本，让测试可以确认 query 和 YAML 候选被正确填入。
    mock_load_prompt = Mock(
        return_value="用户问题：{query}\n候选指标：\n{metric_infos}"
    )
    monkeypatch.setattr(filter_metric_module, "load_prompt", mock_load_prompt)

    # 使用 Mock 包住 yaml.dump，既验证序列化参数，也让填充后的 Prompt 更易断言。
    mock_yaml_dump = Mock(return_value="METRIC_INFOS_YAML")
    monkeypatch.setattr(filter_metric_module.yaml, "dump", mock_yaml_dump)

    received_prompts: list[str] = []

    def fake_llm(prompt_value: Any) -> AIMessage:
        """记录填充后的 Prompt，并返回包含重复项和未知项的指标名称。"""

        received_prompts.append(prompt_value.to_string())
        return AIMessage(
            content=json.dumps(
                ["GMV", "GMV", "不存在的指标"],
                ensure_ascii=False,
            )
        )

    monkeypatch.setattr(
        filter_metric_module,
        "llm",
        RunnableLambda(fake_llm),
    )

    state = DataAgentState(
        query="查询华东地区的销售总额",
        metric_infos=metric_infos,
    )
    result = await filter_metric_module.filter_metric(
        state,
        create_runtime(writer),
    )

    mock_load_prompt.assert_called_once_with("filter_metric_info")
    mock_yaml_dump.assert_called_once_with(
        metric_infos,
        allow_unicode=True,
        sort_keys=False,
    )
    assert received_prompts == [
        "用户问题：查询华东地区的销售总额\n候选指标：\nMETRIC_INFOS_YAML"
    ]

    # “不存在的指标”不在原始候选中，所以不能被程序凭空创建；重复的 GMV
    # 也只会保留原候选列表中的一个完整对象。
    assert result == {"metric_infos": [metric_infos[0]]}
    assert result["metric_infos"][0] is metric_infos[0]
    assert result["metric_infos"][0]["relevant_columns"] == [
        "fact_order.order_amount",
        "fact_order.order_status",
    ]
    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤指标信息", "status": "running"}),
        call({"type": "progress", "step": "过滤指标信息", "status": "success"}),
    ]


async def test_filter_metric_allows_empty_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """问题不需要度量指标时，LLM 可以选择空数组并正常返回。"""

    writer = Mock()
    monkeypatch.setattr(
        filter_metric_module,
        "llm",
        create_json_llm([]),
    )

    result = await filter_metric_module.filter_metric(
        DataAgentState(
            query="列出华东地区的订单编号",
            metric_infos=create_metric_infos(),
        ),
        create_runtime(writer),
    )

    assert result == {"metric_infos": []}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤指标信息", "status": "running"}),
        call({"type": "progress", "step": "过滤指标信息", "status": "success"}),
    ]


@pytest.mark.parametrize(
    "invalid_result",
    [
        {"metric": "GMV"},
        "GMV",
        ["GMV", 123],
    ],
    ids=["json-object", "json-string", "mixed-list"],
)
async def test_filter_metric_rejects_invalid_result_structure(
    monkeypatch: pytest.MonkeyPatch,
    invalid_result: Any,
) -> None:
    """合法 JSON 若不是纯字符串数组，也必须报告错误而不能进入 State。"""

    writer = Mock()
    monkeypatch.setattr(
        filter_metric_module,
        "llm",
        create_json_llm(invalid_result),
    )

    with pytest.raises(
        ValueError,
        match="指标过滤模型必须返回由指标名称组成的 JSON 字符串数组",
    ):
        await filter_metric_module.filter_metric(
            DataAgentState(
                query="查询销售总额",
                metric_infos=create_metric_infos(),
            ),
            create_runtime(writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤指标信息", "status": "running"}),
        call({"type": "progress", "step": "过滤指标信息", "status": "error"}),
    ]


async def test_filter_metric_reports_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用失败时发送 error，并将原始异常继续抛给 LangGraph。"""

    async def failing_llm(_: Any) -> AIMessage:
        raise RuntimeError("llm unavailable")

    writer = Mock()
    monkeypatch.setattr(
        filter_metric_module,
        "llm",
        RunnableLambda(failing_llm),
    )

    with pytest.raises(RuntimeError, match="llm unavailable"):
        await filter_metric_module.filter_metric(
            DataAgentState(
                query="查询销售总额",
                metric_infos=create_metric_infos(),
            ),
            create_runtime(writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤指标信息", "status": "running"}),
        call({"type": "progress", "step": "过滤指标信息", "status": "error"}),
    ]
