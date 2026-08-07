"""测试在线 Agent 的候选表与字段过滤节点。"""

import copy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app.agent.nodes.filter_table as filter_table_module
from app.agent.state import ColumnInfoState, DataAgentState, TableInfoState


def create_json_llm(value: Any) -> RunnableLambda:
    """创建返回固定 JSON 内容的 LangChain Runnable。"""

    # 测试保留真实 PromptTemplate 和 JsonOutputParser，只替换远端 LLM 调用，
    # 因而既能覆盖 LCEL 管道，又不会访问网络或消耗模型额度。
    return RunnableLambda(
        lambda _: AIMessage(
            content=json.dumps(value, ensure_ascii=False),
        )
    )


def create_column(
    *,
    name: str,
    column_type: str,
    role: str,
    examples: list | None = None,
    description: str,
    alias: list[str] | None = None,
) -> ColumnInfoState:
    """创建一个供表过滤测试使用的字段 State。"""

    return ColumnInfoState(
        name=name,
        type=column_type,
        role=role,
        examples=[] if examples is None else examples,
        description=description,
        alias=[] if alias is None else alias,
    )


def create_table_infos() -> list[TableInfoState]:
    """构造订单、地区和商品三张候选表。"""

    return [
        TableInfoState(
            name="fact_order",
            role="fact",
            description="订单事实表。",
            columns=[
                create_column(
                    name="order_id",
                    column_type="bigint",
                    role="primary_key",
                    description="订单主键。",
                ),
                create_column(
                    name="order_amount",
                    column_type="decimal(10,2)",
                    role="measure",
                    examples=[100.0, 268.0],
                    description="订单成交金额。",
                    alias=["销售额", "订单金额"],
                ),
                create_column(
                    name="order_status",
                    column_type="varchar(32)",
                    role="dimension",
                    examples=["已支付", "已取消"],
                    description="订单状态。",
                    alias=["支付状态"],
                ),
                create_column(
                    name="region_id",
                    column_type="bigint",
                    role="foreign_key",
                    description="订单所属地区。",
                ),
            ],
        ),
        TableInfoState(
            name="dim_region",
            role="dimension",
            description="地区维度表。",
            columns=[
                create_column(
                    name="region_id",
                    column_type="bigint",
                    role="primary_key",
                    description="地区主键。",
                ),
                create_column(
                    name="region_name",
                    column_type="varchar(64)",
                    role="dimension",
                    examples=["华北", "华东"],
                    description="地区名称。",
                    alias=["区域"],
                ),
            ],
        ),
        TableInfoState(
            name="dim_product",
            role="dimension",
            description="商品维度表。",
            columns=[
                create_column(
                    name="product_id",
                    column_type="bigint",
                    role="primary_key",
                    description="商品主键。",
                ),
                create_column(
                    name="product_name",
                    column_type="varchar(128)",
                    role="dimension",
                    description="商品名称。",
                ),
            ],
        ),
    ]


def create_runtime(writer: Mock) -> SimpleNamespace:
    """创建只提供 stream_writer 的轻量 Runtime 替身。"""

    # filter_table 不访问 DataAgentContext 中的任何 Repository 或客户端。
    return SimpleNamespace(stream_writer=writer, context={})


async def test_filter_table_selects_original_tables_and_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型只给名称，程序从原候选中构造新的可信表字段结构。"""

    table_infos = create_table_infos()
    original_table_infos = copy.deepcopy(table_infos)
    writer = Mock()

    # 固定 Prompt 内容，确认 query 和 YAML 候选真正进入 LCEL 链。
    mock_load_prompt = Mock(return_value="用户问题：{query}\n候选表：\n{table_infos}")
    monkeypatch.setattr(filter_table_module, "load_prompt", mock_load_prompt)

    mock_yaml_dump = Mock(return_value="TABLE_INFOS_YAML")
    monkeypatch.setattr(filter_table_module.yaml, "dump", mock_yaml_dump)

    received_prompts: list[str] = []

    def fake_llm(prompt_value: Any) -> AIMessage:
        """记录 Prompt，并返回包含重复项和未知项的表字段选择。"""

        received_prompts.append(prompt_value.to_string())
        return AIMessage(
            content=json.dumps(
                {
                    # 重复 region_id 应自然去重，unknown_column 不能被创建。
                    "fact_order": [
                        "order_amount",
                        "order_status",
                        "region_id",
                        "region_id",
                        "unknown_column",
                    ],
                    # 两张表都保留 region_id，模拟多表 JOIN 所需主外键。
                    "dim_region": ["region_id", "region_name"],
                    # dim_product 只选择不存在字段，过滤后为空，整表应被删除。
                    "dim_product": ["unknown_product_column"],
                    # 完全不存在的表也不能凭空进入最终 State。
                    "unknown_table": ["unknown_column"],
                },
                ensure_ascii=False,
            )
        )

    monkeypatch.setattr(
        filter_table_module,
        "llm",
        RunnableLambda(fake_llm),
    )

    result = await filter_table_module.filter_table(
        DataAgentState(
            query="查询华东地区的销售总额",
            table_infos=table_infos,
        ),
        create_runtime(writer),
    )

    mock_load_prompt.assert_called_once_with("filter_table_info")
    mock_yaml_dump.assert_called_once_with(
        table_infos,
        allow_unicode=True,
        sort_keys=False,
    )
    assert received_prompts == [
        "用户问题：查询华东地区的销售总额\n候选表：\nTABLE_INFOS_YAML"
    ]

    # 最终只保留原候选中真实存在、且至少包含一个有效字段的两张表。
    assert [table_info["name"] for table_info in result["table_infos"]] == [
        "fact_order",
        "dim_region",
    ]
    assert [
        column_info["name"] for column_info in result["table_infos"][0]["columns"]
    ] == ["order_amount", "order_status", "region_id"]
    assert [
        column_info["name"] for column_info in result["table_infos"][1]["columns"]
    ] == ["region_id", "region_name"]

    # 字段的类型、角色、样例、描述和别名均来自原始可信结构，而不是 LLM。
    order_amount = result["table_infos"][0]["columns"][0]
    assert order_amount == {
        "name": "order_amount",
        "type": "decimal(10,2)",
        "role": "measure",
        "examples": [100.0, 268.0],
        "description": "订单成交金额。",
        "alias": ["销售额", "订单金额"],
    }

    # rebuild 不原地改写输入 TableInfoState：候选表和候选字段保持完整，
    # 新结果中的表字典则是单独创建的对象。
    assert table_infos == original_table_infos
    assert result["table_infos"][0] is not table_infos[0]
    assert result["table_infos"][1] is not table_infos[1]

    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤表信息", "status": "running"}),
        call({"type": "progress", "step": "过滤表信息", "status": "success"}),
    ]


async def test_filter_table_allows_empty_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前问题不需要任何候选表时，空 JSON 对象是合法选择。"""

    writer = Mock()
    monkeypatch.setattr(
        filter_table_module,
        "llm",
        create_json_llm({}),
    )

    result = await filter_table_module.filter_table(
        DataAgentState(
            query="你好",
            table_infos=create_table_infos(),
        ),
        create_runtime(writer),
    )

    assert result == {"table_infos": []}
    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤表信息", "status": "running"}),
        call({"type": "progress", "step": "过滤表信息", "status": "success"}),
    ]


@pytest.mark.parametrize(
    "invalid_result",
    [
        ["fact_order", "dim_region"],
        "fact_order",
        {"fact_order": "order_amount"},
        {"fact_order": ["order_amount", 123]},
    ],
    ids=[
        "json-list",
        "json-string",
        "column-not-list",
        "mixed-column-list",
    ],
)
async def test_filter_table_rejects_invalid_result_structure(
    monkeypatch: pytest.MonkeyPatch,
    invalid_result: Any,
) -> None:
    """合法 JSON 若不符合表名到字符串字段列表的映射，也必须终止节点。"""

    writer = Mock()
    monkeypatch.setattr(
        filter_table_module,
        "llm",
        create_json_llm(invalid_result),
    )

    with pytest.raises(
        ValueError,
        match="表过滤模型必须返回.*JSON 对象",
    ):
        await filter_table_module.filter_table(
            DataAgentState(
                query="查询销售总额",
                table_infos=create_table_infos(),
            ),
            create_runtime(writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤表信息", "status": "running"}),
        call({"type": "progress", "step": "过滤表信息", "status": "error"}),
    ]


async def test_filter_table_reports_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用失败时发送 error，并将原始异常继续抛给 LangGraph。"""

    async def failing_llm(_: Any) -> AIMessage:
        raise RuntimeError("llm unavailable")

    writer = Mock()
    monkeypatch.setattr(
        filter_table_module,
        "llm",
        RunnableLambda(failing_llm),
    )

    with pytest.raises(RuntimeError, match="llm unavailable"):
        await filter_table_module.filter_table(
            DataAgentState(
                query="查询销售总额",
                table_infos=create_table_infos(),
            ),
            create_runtime(writer),
        )

    assert writer.call_args_list == [
        call({"type": "progress", "step": "过滤表信息", "status": "running"}),
        call({"type": "progress", "step": "过滤表信息", "status": "error"}),
    ]
