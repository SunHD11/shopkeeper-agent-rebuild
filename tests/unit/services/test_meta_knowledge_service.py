"""测试 MetaKnowledgeService 的实体组装、索引构建和总流程编排。"""

from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import UUID

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.conf.meta_config import (
    ColumnConfig,
    MetaConfig,
    MetricConfig,
    TableConfig,
)
from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import (
    ColumnQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import (
    MetricQdrantRepository,
)
from app.services.meta_knowledge_service import MetaKnowledgeService


def create_service() -> tuple[
    MetaKnowledgeService,
    Mock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    """创建注入了 Mock 依赖的 Service，避免访问任何真实外部服务。"""

    meta_repository = Mock(spec=MetaMySQLRepository)
    meta_repository.session = Mock()
    meta_repository.session.begin.return_value = AsyncMock()

    dw_repository = AsyncMock(spec=DWMySQLRepository)
    column_repository = AsyncMock(spec=ColumnQdrantRepository)
    embedding_client = AsyncMock(spec=HuggingFaceEndpointEmbeddings)
    value_repository = AsyncMock(spec=ValueESRepository)
    metric_repository = AsyncMock(spec=MetricQdrantRepository)

    service = MetaKnowledgeService(
        meta_mysql_repository=meta_repository,
        dw_mysql_repository=dw_repository,
        column_qdrant_repository=column_repository,
        embedding_client=embedding_client,
        value_es_repository=value_repository,
        metric_qdrant_repository=metric_repository,
    )

    return (
        service,
        meta_repository,
        dw_repository,
        column_repository,
        embedding_client,
        value_repository,
        metric_repository,
    )


def create_table_config() -> TableConfig:
    """创建包含度量字段和维度字段的最小表配置。"""

    return TableConfig(
        name="fact_order",
        role="fact",
        description="订单事实表。",
        columns=[
            ColumnConfig(
                name="order_amount",
                role="measure",
                description="订单金额。",
                alias=["销售额", "收入"],
                sync=False,
            ),
            ColumnConfig(
                name="region_name",
                role="dimension",
                description="订单所属大区。",
                alias=["地区", "大区"],
                sync=True,
            ),
        ],
    )


def create_metric_config() -> MetricConfig:
    """创建一个依赖两个字段的指标配置。"""

    return MetricConfig(
        name="GMV",
        description="所有订单成交金额总和。",
        relevant_columns=[
            "fact_order.order_amount",
            "fact_order.region_name",
        ],
        alias=["成交总额", "订单总额"],
    )


async def test_save_tables_combines_yaml_and_dw_metadata() -> None:
    """YAML 业务语义和 DW 类型、示例值会组合成表字段实体。"""

    (
        service,
        meta_repository,
        dw_repository,
        _,
        _,
        _,
        _,
    ) = create_service()
    meta_config = MetaConfig(tables=[create_table_config()])
    dw_repository.get_column_types.return_value = {
        "order_amount": "decimal(10,2)",
        "region_name": "varchar(32)",
    }
    dw_repository.get_column_values.side_effect = [
        [100.0, 268.0],
        ["华东", "华南"],
    ]

    column_infos = await service._save_tables_to_meta_db(meta_config)

    expected_table_infos = [
        TableInfo(
            id="fact_order",
            name="fact_order",
            role="fact",
            description="订单事实表。",
        )
    ]
    expected_column_infos = [
        ColumnInfo(
            id="fact_order.order_amount",
            name="order_amount",
            type="decimal(10,2)",
            role="measure",
            examples=[100.0, 268.0],
            description="订单金额。",
            alias=["销售额", "收入"],
            table_id="fact_order",
        ),
        ColumnInfo(
            id="fact_order.region_name",
            name="region_name",
            type="varchar(32)",
            role="dimension",
            examples=["华东", "华南"],
            description="订单所属大区。",
            alias=["地区", "大区"],
            table_id="fact_order",
        ),
    ]

    assert column_infos == expected_column_infos
    dw_repository.get_column_types.assert_awaited_once_with("fact_order")
    assert dw_repository.get_column_values.await_args_list == [
        call("fact_order", "order_amount"),
        call("fact_order", "region_name"),
    ]
    meta_repository.session.begin.assert_called_once_with()
    meta_repository.save_table_infos.assert_awaited_once_with(expected_table_infos)
    meta_repository.save_column_infos.assert_awaited_once_with(expected_column_infos)


async def test_save_column_info_builds_name_description_and_alias_points() -> None:
    """一个字段的名称、描述和每个别名都会成为独立向量入口。"""

    service, _, _, column_repository, embedding_client, _, _ = create_service()
    column_info = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0],
        description="订单金额。",
        alias=["销售额", "收入"],
        table_id="fact_order",
    )
    point_ids = [UUID(int=index) for index in range(1, 5)]
    embeddings = [[0.1], [0.2], [0.3], [0.4]]
    embedding_client.aembed_documents.return_value = embeddings

    with patch(
        "app.services.meta_knowledge_service.uuid.uuid5",
        side_effect=point_ids,
    ):
        await service._save_column_info_to_qdrant([column_info])

    column_repository.ensure_collection.assert_awaited_once_with()
    embedding_client.aembed_documents.assert_awaited_once_with(
        ["order_amount", "订单金额。", "销售额", "收入"]
    )
    column_repository.upsert.assert_awaited_once_with(
        point_ids,
        embeddings,
        [asdict(column_info)] * 4,
    )


async def test_save_column_info_embeds_texts_in_batches_of_twenty() -> None:
    """字段检索文本超过 20 条时会拆分成多个 Embedding 请求。"""

    service, _, _, column_repository, embedding_client, _, _ = create_service()
    aliases = [f"别名{index}" for index in range(19)]
    column_info = ColumnInfo(
        id="fact_order.order_amount",
        name="order_amount",
        type="decimal(10,2)",
        role="measure",
        examples=[100.0],
        description="订单金额。",
        alias=aliases,
        table_id="fact_order",
    )
    embedding_texts = ["order_amount", "订单金额。", *aliases]
    point_ids = [UUID(int=index) for index in range(1, 22)]
    embeddings = [[float(index)] for index in range(21)]
    embedding_client.aembed_documents.side_effect = [
        embeddings[:20],
        embeddings[20:],
    ]

    with patch(
        "app.services.meta_knowledge_service.uuid.uuid5",
        side_effect=point_ids,
    ):
        await service._save_column_info_to_qdrant([column_info])

    assert embedding_client.aembed_documents.await_args_list == [
        call(embedding_texts[:20]),
        call(embedding_texts[20:]),
    ]
    column_repository.upsert.assert_awaited_once_with(
        point_ids,
        embeddings,
        [asdict(column_info)] * 21,
    )


async def test_save_value_info_only_indexes_sync_enabled_columns() -> None:
    """只有 YAML 中 sync=True 的字段才会读取大量真实值并写入 ES。"""

    service, _, dw_repository, _, _, value_repository, _ = create_service()
    table_config = create_table_config()
    meta_config = MetaConfig(tables=[table_config])
    column_infos = [
        ColumnInfo(
            id="fact_order.order_amount",
            name="order_amount",
            type="decimal(10,2)",
            role="measure",
            examples=[100.0],
            description="订单金额。",
            alias=["销售额", "收入"],
            table_id="fact_order",
        ),
        ColumnInfo(
            id="fact_order.region_name",
            name="region_name",
            type="varchar(32)",
            role="dimension",
            examples=["华东"],
            description="订单所属大区。",
            alias=["地区", "大区"],
            table_id="fact_order",
        ),
    ]
    dw_repository.get_column_values.return_value = ["华东", "华南"]

    await service._save_value_info_to_es(meta_config, column_infos)

    value_repository.ensure_index.assert_awaited_once_with()
    dw_repository.get_column_values.assert_awaited_once_with(
        "fact_order",
        "region_name",
        100000,
    )
    value_repository.index.assert_awaited_once_with(
        [
            ValueInfo(
                id="fact_order.region_name.华东",
                value="华东",
                column_id="fact_order.region_name",
            ),
            ValueInfo(
                id="fact_order.region_name.华南",
                value="华南",
                column_id="fact_order.region_name",
            ),
        ]
    )


async def test_save_metrics_builds_metric_and_column_relationships() -> None:
    """指标配置会转换成 MetricInfo 和每条字段依赖关系。"""

    service, meta_repository, _, _, _, _, _ = create_service()
    meta_config = MetaConfig(metrics=[create_metric_config()])

    metric_infos = await service._save_metrics_to_meta_db(meta_config)

    expected_metric_infos = [
        MetricInfo(
            id="GMV",
            name="GMV",
            description="所有订单成交金额总和。",
            relevant_columns=[
                "fact_order.order_amount",
                "fact_order.region_name",
            ],
            alias=["成交总额", "订单总额"],
        )
    ]
    expected_column_metrics = [
        ColumnMetric(
            column_id="fact_order.order_amount",
            metric_id="GMV",
        ),
        ColumnMetric(
            column_id="fact_order.region_name",
            metric_id="GMV",
        ),
    ]

    assert metric_infos == expected_metric_infos
    meta_repository.session.begin.assert_called_once_with()
    meta_repository.save_metric_infos.assert_awaited_once_with(expected_metric_infos)
    meta_repository.save_column_metrics.assert_awaited_once_with(
        expected_column_metrics
    )


async def test_save_metrics_builds_name_description_and_alias_points() -> None:
    """指标名称、描述和每个别名都会成为独立向量入口。"""

    service, _, _, _, embedding_client, _, metric_repository = create_service()
    metric_info = MetricInfo(
        id="GMV",
        name="GMV",
        description="所有订单成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额", "订单总额"],
    )
    point_ids = [UUID(int=index) for index in range(1, 5)]
    embeddings = [[0.1], [0.2], [0.3], [0.4]]
    embedding_client.aembed_documents.return_value = embeddings

    with patch(
        "app.services.meta_knowledge_service.uuid.uuid5",
        side_effect=point_ids,
    ):
        await service._save_metrics_to_qdrant([metric_info])

    metric_repository.ensure_collection.assert_awaited_once_with()
    embedding_client.aembed_documents.assert_awaited_once_with(
        ["GMV", "所有订单成交金额总和。", "成交总额", "订单总额"]
    )
    metric_repository.upsert.assert_awaited_once_with(
        point_ids,
        embeddings,
        [asdict(metric_info)] * 4,
    )


async def test_build_runs_full_pipeline_in_business_order(
    tmp_path: Path,
) -> None:
    """配置同时包含表和指标时，五个构建步骤必须按业务顺序执行。"""

    service, _, _, _, _, _, _ = create_service()
    config_path = tmp_path / "meta_config.yaml"
    config_path.write_text(
        """
tables:
  - name: fact_order
    role: fact
    description: 订单事实表。
    columns:
      - name: order_amount
        role: measure
        description: 订单金额。
        alias: [销售额]
        sync: false
metrics:
  - name: GMV
    description: 所有订单成交金额总和。
    relevant_columns: [fact_order.order_amount]
    alias: [成交总额]
""".strip(),
        encoding="utf-8",
    )
    column_infos = [
        ColumnInfo(
            id="fact_order.order_amount",
            name="order_amount",
            type="decimal(10,2)",
            role="measure",
            examples=[100.0],
            description="订单金额。",
            alias=["销售额"],
            table_id="fact_order",
        )
    ]
    metric_infos = [
        MetricInfo(
            id="GMV",
            name="GMV",
            description="所有订单成交金额总和。",
            relevant_columns=["fact_order.order_amount"],
            alias=["成交总额"],
        )
    ]
    execution_order: list[str] = []

    async def save_tables(meta_config: MetaConfig) -> list[ColumnInfo]:
        assert meta_config.tables is not None
        execution_order.append("save_tables")
        return column_infos

    async def save_columns(columns: list[ColumnInfo]) -> None:
        assert columns == column_infos
        execution_order.append("save_columns")

    async def save_values(
        meta_config: MetaConfig,
        columns: list[ColumnInfo],
    ) -> None:
        assert meta_config.tables is not None
        assert columns == column_infos
        execution_order.append("save_values")

    async def save_metrics(meta_config: MetaConfig) -> list[MetricInfo]:
        assert meta_config.metrics is not None
        execution_order.append("save_metrics")
        return metric_infos

    async def save_metric_vectors(metrics: list[MetricInfo]) -> None:
        assert metrics == metric_infos
        execution_order.append("save_metric_vectors")

    service._save_tables_to_meta_db = AsyncMock(side_effect=save_tables)
    service._save_column_info_to_qdrant = AsyncMock(side_effect=save_columns)
    service._save_value_info_to_es = AsyncMock(side_effect=save_values)
    service._save_metrics_to_meta_db = AsyncMock(side_effect=save_metrics)
    service._save_metrics_to_qdrant = AsyncMock(side_effect=save_metric_vectors)

    await service.build(config_path)

    assert execution_order == [
        "save_tables",
        "save_columns",
        "save_values",
        "save_metrics",
        "save_metric_vectors",
    ]


async def test_build_skips_metric_pipeline_when_metrics_are_missing(
    tmp_path: Path,
) -> None:
    """只有 tables 配置时，不应执行任何指标构建步骤。"""

    service, _, _, _, _, _, _ = create_service()
    config_path = tmp_path / "tables_only.yaml"
    config_path.write_text(
        """
tables:
  - name: fact_order
    role: fact
    description: 订单事实表。
    columns:
      - name: order_amount
        role: measure
        description: 订单金额。
        alias: [销售额]
        sync: false
""".strip(),
        encoding="utf-8",
    )
    service._save_tables_to_meta_db = AsyncMock(return_value=[])
    service._save_column_info_to_qdrant = AsyncMock()
    service._save_value_info_to_es = AsyncMock()
    service._save_metrics_to_meta_db = AsyncMock()
    service._save_metrics_to_qdrant = AsyncMock()

    await service.build(config_path)

    service._save_tables_to_meta_db.assert_awaited_once()
    service._save_column_info_to_qdrant.assert_awaited_once_with([])
    service._save_value_info_to_es.assert_awaited_once()
    service._save_metrics_to_meta_db.assert_not_awaited()
    service._save_metrics_to_qdrant.assert_not_awaited()


async def test_build_skips_table_pipeline_when_tables_are_missing(
    tmp_path: Path,
) -> None:
    """只有 metrics 配置时，不应执行任何表字段构建步骤。"""

    service, _, _, _, _, _, _ = create_service()
    config_path = tmp_path / "metrics_only.yaml"
    config_path.write_text(
        """
metrics:
  - name: GMV
    description: 所有订单成交金额总和。
    relevant_columns: [fact_order.order_amount]
    alias: [成交总额]
""".strip(),
        encoding="utf-8",
    )
    service._save_tables_to_meta_db = AsyncMock()
    service._save_column_info_to_qdrant = AsyncMock()
    service._save_value_info_to_es = AsyncMock()
    service._save_metrics_to_meta_db = AsyncMock(return_value=[])
    service._save_metrics_to_qdrant = AsyncMock()

    await service.build(config_path)

    service._save_tables_to_meta_db.assert_not_awaited()
    service._save_column_info_to_qdrant.assert_not_awaited()
    service._save_value_info_to_es.assert_not_awaited()
    service._save_metrics_to_meta_db.assert_awaited_once()
    service._save_metrics_to_qdrant.assert_awaited_once_with([])
