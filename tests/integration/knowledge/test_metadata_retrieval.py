"""使用 rebuild 独立服务验证三类元数据召回。"""

import pytest
from sqlalchemy import text

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

pytestmark = pytest.mark.integration


async def test_real_metadata_retrieval_across_qdrant_and_elasticsearch() -> None:
    """销售额、成交总额和华东应分别命中字段、指标与字段值。"""

    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()

    try:
        qdrant = qdrant_client_manager.require_client()
        embedding = embedding_client_manager.require_client()
        elasticsearch = es_client_manager.require_client()

        column_repository = ColumnQdrantRepository(qdrant)
        metric_repository = MetricQdrantRepository(qdrant)
        value_repository = ValueESRepository(elasticsearch)

        column_vector = await embedding.aembed_query("销售额")
        columns = await column_repository.search(column_vector, score_threshold=0.5)
        assert "fact_order.order_amount" in {column.id for column in columns}

        metric_vector = await embedding.aembed_query("成交总额")
        metrics = await metric_repository.search(metric_vector, score_threshold=0.5)
        assert "GMV" in {metric.id for metric in metrics}

        values = await value_repository.search("华东", score_threshold=0.5)
        assert "dim_region.region_name" in {value.column_id for value in values}
    finally:
        await es_client_manager.close()
        await embedding_client_manager.close()
        await qdrant_client_manager.close()


async def test_rebuild_knowledge_store_has_expected_complete_counts() -> None:
    """三套存储应与当前教学配置包含的元数据数量一致。"""

    meta_mysql_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()

    try:
        session_factory = meta_mysql_client_manager.require_session_factory()
        async with session_factory() as session:
            table_count = await session.scalar(text("SELECT COUNT(*) FROM table_info"))
            column_count = await session.scalar(
                text("SELECT COUNT(*) FROM column_info")
            )
            metric_count = await session.scalar(
                text("SELECT COUNT(*) FROM metric_info")
            )
            relation_count = await session.scalar(
                text("SELECT COUNT(*) FROM column_metric")
            )

        assert (table_count, column_count, metric_count, relation_count) == (
            5,
            24,
            2,
            2,
        )

        qdrant = qdrant_client_manager.require_client()
        column_points = await qdrant.count(
            collection_name=app_config.qdrant.column_collection_name,
            exact=True,
        )
        metric_points = await qdrant.count(
            collection_name=app_config.qdrant.metric_collection_name,
            exact=True,
        )
        assert column_points.count == 98
        assert metric_points.count == 8

        elasticsearch = es_client_manager.require_client()
        value_count = await elasticsearch.count(index=app_config.es.index_name)
        assert value_count["count"] == 75
    finally:
        await es_client_manager.close()
        await qdrant_client_manager.close()
        await meta_mysql_client_manager.close()
