"""测试三路召回信息合并节点。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.state import DataAgentState
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo


def create_column(
    column_id: str,
    *,
    name: str,
    role: str,
    table_id: str,
    column_type: str = "varchar(64)",
    examples: list | None = None,
    description: str = "字段说明。",
    alias: list[str] | None = None,
) -> ColumnInfo:
    """创建测试字段，减少不同测试中与关注点无关的重复参数。"""

    return ColumnInfo(
        id=column_id,
        name=name,
        type=column_type,
        role=role,
        examples=[] if examples is None else examples,
        description=description,
        alias=[] if alias is None else alias,
        table_id=table_id,
    )


def create_runtime(
    repository: Mock,
    writer: Mock,
) -> SimpleNamespace:
    """构造只包含合并节点所需依赖的轻量 Runtime 替身。"""

    # merge_retrieved_info 只使用 stream_writer 和 meta_mysql_repository，
    # 不需要创建真正的 LangGraph Runtime，也不会连接真实 Meta MySQL。
    return SimpleNamespace(
        stream_writer=writer,
        context={"meta_mysql_repository": repository},
    )


async def test_merge_retrieved_info_builds_complete_context() -> None:
    """三路候选能够完成字段补齐、取值回填、主外键补齐和按表组装。"""

    # ------------------------- 准备字段召回结果 -------------------------

    # order_amount 模拟字段召回命中的订单金额字段。
    order_amount = create_column(
        "fact_order.order_amount",
        name="order_amount",
        role="measure",
        table_id="fact_order",
        column_type="decimal(10,2)",
        examples=[100.0],
        description="订单成交金额。",
        alias=["销售额", "订单金额"],
    )

    # 使用相同业务 id 创建一个旧版本，验证节点会根据 ColumnInfo.id 去重。
    # 字典推导式会保留列表中最后出现的 order_amount。
    old_order_amount = create_column(
        "fact_order.order_amount",
        name="order_amount",
        role="measure",
        table_id="fact_order",
        column_type="decimal(10,2)",
        description="不应进入最终结果的重复字段。",
    )

    # 外键已经被字段召回命中；稍后主外键查询会再次返回它，
    # 用于验证主外键补齐不会制造重复字段。
    fact_region_id = create_column(
        "fact_order.region_id",
        name="region_id",
        role="foreign_key",
        table_id="fact_order",
        column_type="bigint",
        description="订单所属地区。",
    )

    # ------------------------- 准备指标召回结果 -------------------------

    # GMV 同时依赖已召回的 order_amount 和尚未召回的 order_status。
    # 节点应该只向 Meta Repository 查询缺失的 order_status。
    gmv = MetricInfo(
        id="GMV",
        name="GMV",
        description="已支付订单的成交总额。",
        relevant_columns=[
            "fact_order.order_amount",
            "fact_order.order_status",
        ],
        alias=["成交总额", "销售总额"],
    )

    order_status = create_column(
        "fact_order.order_status",
        name="order_status",
        role="dimension",
        table_id="fact_order",
        examples=["已支付"],
        description="订单状态。",
        alias=["支付状态"],
    )

    # ------------------------ 准备字段值召回结果 ------------------------

    # region_name 没有被字段召回直接命中，只有 ES 返回的 ValueInfo 指向它。
    # 节点应该先从 Meta MySQL 补齐字段，再把“华东”追加进 examples。
    region_name = create_column(
        "dim_region.region_name",
        name="region_name",
        role="dimension",
        table_id="dim_region",
        examples=["华北"],
        description="地区名称。",
        alias=["区域"],
    )
    east_china = ValueInfo(
        id="dim_region.region_name.华东",
        value="华东",
        column_id="dim_region.region_name",
    )

    # 重复值模拟同一个真实值被多个关键词命中。虽然 recall_value 已经会按 id
    # 去重，合并节点仍会保护 examples，不允许“华东”被重复追加。
    duplicate_east_china = ValueInfo(
        id="dim_region.region_name.华东.duplicate",
        value="华东",
        column_id="dim_region.region_name",
    )

    # ------------------------- 准备主外键和表 ---------------------------

    order_id = create_column(
        "fact_order.order_id",
        name="order_id",
        role="primary_key",
        table_id="fact_order",
        column_type="bigint",
        description="订单主键。",
    )
    dim_region_id = create_column(
        "dim_region.region_id",
        name="region_id",
        role="primary_key",
        table_id="dim_region",
        column_type="bigint",
        description="地区主键。",
    )

    fact_order = TableInfo(
        id="fact_order",
        name="fact_order",
        role="fact",
        description="订单事实表。",
    )
    dim_region = TableInfo(
        id="dim_region",
        name="dim_region",
        role="dimension",
        description="地区维度表。",
    )

    repository = Mock()

    # 按字段 id 返回指标和值链路缺失的字段。
    missing_columns = {
        order_status.id: order_status,
        region_name.id: region_name,
    }
    repository.get_column_info_by_id = AsyncMock(
        side_effect=lambda column_id: missing_columns.get(column_id)
    )

    # fact_order 的查询结果故意再次包含 fact_region_id，验证 setdefault 去重；
    # dim_region 则补入生成 JOIN 所需的主键。
    key_columns = {
        "fact_order": [fact_region_id, order_id],
        "dim_region": [dim_region_id],
    }
    repository.get_key_columns_by_table_id = AsyncMock(
        side_effect=lambda table_id: key_columns[table_id]
    )

    tables = {
        fact_order.id: fact_order,
        dim_region.id: dim_region,
    }
    repository.get_table_info_by_id = AsyncMock(
        side_effect=lambda table_id: tables.get(table_id)
    )

    writer = Mock()
    runtime = create_runtime(repository, writer)
    state = DataAgentState(
        query="查询华东地区的销售总额",
        keywords=["华东", "销售总额"],
        retrieved_column_infos=[
            old_order_amount,
            order_amount,
            fact_region_id,
        ],
        retrieved_metric_infos=[gmv],
        retrieved_value_infos=[east_china, duplicate_east_china],
    )

    result = await merge_retrieved_info(state, runtime)

    # ---------------------------- 验证查询行为 ---------------------------

    # 已直接召回的 order_amount 和 fact_region_id 不应再次查询；
    # 只有指标缺失字段和字段值所属字段需要按 id 补齐。
    assert repository.get_column_info_by_id.await_args_list == [
        call("fact_order.order_status"),
        call("dim_region.region_name"),
    ]
    assert repository.get_key_columns_by_table_id.await_args_list == [
        call("fact_order"),
        call("dim_region"),
    ]
    assert repository.get_table_info_by_id.await_args_list == [
        call("fact_order"),
        call("dim_region"),
    ]

    # ---------------------------- 验证表上下文 ---------------------------

    table_infos = {
        table_info["name"]: table_info for table_info in result["table_infos"]
    }
    assert set(table_infos) == {"fact_order", "dim_region"}

    fact_columns = {
        column_info["name"]: column_info
        for column_info in table_infos["fact_order"]["columns"]
    }
    assert set(fact_columns) == {
        "order_amount",
        "region_id",
        "order_status",
        "order_id",
    }
    assert fact_columns["order_amount"] == {
        "name": "order_amount",
        "type": "decimal(10,2)",
        "role": "measure",
        "examples": [100.0],
        "description": "订单成交金额。",
        "alias": ["销售额", "订单金额"],
    }
    assert fact_columns["region_id"]["role"] == "foreign_key"
    assert fact_columns["order_id"]["role"] == "primary_key"
    assert fact_columns["order_status"]["examples"] == ["已支付"]

    region_columns = {
        column_info["name"]: column_info
        for column_info in table_infos["dim_region"]["columns"]
    }
    assert set(region_columns) == {"region_name", "region_id"}
    assert region_columns["region_name"]["examples"] == ["华北", "华东"]
    assert region_columns["region_id"]["role"] == "primary_key"

    # --------------------------- 验证指标和事件 ---------------------------

    assert result["metric_infos"] == [
        {
            "name": "GMV",
            "description": "已支付订单的成交总额。",
            "relevant_columns": [
                "fact_order.order_amount",
                "fact_order.order_status",
            ],
            "alias": ["成交总额", "销售总额"],
        }
    ]
    assert writer.call_args_list == [
        call({"type": "progress", "step": "合并召回信息", "status": "running"}),
        call({"type": "progress", "step": "合并召回信息", "status": "success"}),
    ]


async def test_merge_retrieved_info_accepts_empty_recall_results() -> None:
    """三路召回都为空时返回空上下文，并且不查询 Meta MySQL。"""

    repository = Mock()
    repository.get_column_info_by_id = AsyncMock()
    repository.get_key_columns_by_table_id = AsyncMock()
    repository.get_table_info_by_id = AsyncMock()
    writer = Mock()

    result = await merge_retrieved_info(
        DataAgentState(
            query="查询不存在的业务概念",
            keywords=[],
            retrieved_column_infos=[],
            retrieved_metric_infos=[],
            retrieved_value_infos=[],
        ),
        create_runtime(repository, writer),
    )

    assert result == {"table_infos": [], "metric_infos": []}
    repository.get_column_info_by_id.assert_not_awaited()
    repository.get_key_columns_by_table_id.assert_not_awaited()
    repository.get_table_info_by_id.assert_not_awaited()
    assert writer.call_args_list == [
        call({"type": "progress", "step": "合并召回信息", "status": "running"}),
        call({"type": "progress", "step": "合并召回信息", "status": "success"}),
    ]


async def test_merge_retrieved_info_reports_missing_metric_column() -> None:
    """指标依赖字段在 Meta MySQL 中不存在时，报告错误并终止合并。"""

    metric = MetricInfo(
        id="GMV",
        name="GMV",
        description="成交总额。",
        relevant_columns=["fact_order.order_amount"],
        alias=["销售总额"],
    )
    repository = Mock()
    repository.get_column_info_by_id = AsyncMock(return_value=None)
    repository.get_key_columns_by_table_id = AsyncMock()
    repository.get_table_info_by_id = AsyncMock()
    writer = Mock()

    with pytest.raises(
        ValueError,
        match=r"指标 GMV 依赖的字段: fact_order\.order_amount",
    ):
        await merge_retrieved_info(
            DataAgentState(
                query="查询销售总额",
                keywords=["销售总额"],
                retrieved_column_infos=[],
                retrieved_metric_infos=[metric],
                retrieved_value_infos=[],
            ),
            create_runtime(repository, writer),
        )

    repository.get_key_columns_by_table_id.assert_not_awaited()
    repository.get_table_info_by_id.assert_not_awaited()
    assert writer.call_args_list == [
        call({"type": "progress", "step": "合并召回信息", "status": "running"}),
        call({"type": "progress", "step": "合并召回信息", "status": "error"}),
    ]


async def test_merge_retrieved_info_reports_missing_value_column() -> None:
    """字段值指向未知字段时，不允许带着不完整 Schema 继续执行。"""

    value_info = ValueInfo(
        id="dim_region.region_name.华东",
        value="华东",
        column_id="dim_region.region_name",
    )
    repository = Mock()
    repository.get_column_info_by_id = AsyncMock(return_value=None)
    repository.get_key_columns_by_table_id = AsyncMock()
    repository.get_table_info_by_id = AsyncMock()
    writer = Mock()

    with pytest.raises(
        ValueError,
        match=r"字段取值 .* 所属的字段: dim_region\.region_name",
    ):
        await merge_retrieved_info(
            DataAgentState(
                query="查询华东地区订单",
                keywords=["华东"],
                retrieved_column_infos=[],
                retrieved_metric_infos=[],
                retrieved_value_infos=[value_info],
            ),
            create_runtime(repository, writer),
        )

    repository.get_key_columns_by_table_id.assert_not_awaited()
    repository.get_table_info_by_id.assert_not_awaited()
    assert writer.call_args_list[-1] == call(
        {"type": "progress", "step": "合并召回信息", "status": "error"}
    )


async def test_merge_retrieved_info_reports_missing_table() -> None:
    """字段所属表在 Meta MySQL 中不存在时，发送 error 并抛出明确异常。"""

    column_info = create_column(
        "fact_unknown.amount",
        name="amount",
        role="measure",
        table_id="fact_unknown",
    )
    repository = Mock()
    repository.get_column_info_by_id = AsyncMock()
    repository.get_key_columns_by_table_id = AsyncMock(return_value=[])
    repository.get_table_info_by_id = AsyncMock(return_value=None)
    writer = Mock()

    with pytest.raises(
        ValueError,
        match="Meta MySQL 中不存在候选表: fact_unknown",
    ):
        await merge_retrieved_info(
            DataAgentState(
                query="查询未知事实表",
                keywords=["未知"],
                retrieved_column_infos=[column_info],
                retrieved_metric_infos=[],
                retrieved_value_infos=[],
            ),
            create_runtime(repository, writer),
        )

    repository.get_column_info_by_id.assert_not_awaited()
    repository.get_key_columns_by_table_id.assert_awaited_once_with("fact_unknown")
    repository.get_table_info_by_id.assert_awaited_once_with("fact_unknown")
    assert writer.call_args_list == [
        call({"type": "progress", "step": "合并召回信息", "status": "running"}),
        call({"type": "progress", "step": "合并召回信息", "status": "error"}),
    ]
