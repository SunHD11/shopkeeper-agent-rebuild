"""测试指标 Qdrant Repository 的集合管理、批量写入和检索转换。"""

from unittest.mock import AsyncMock, Mock, call

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance

from app.conf.app_config import app_config
from app.entities.metric_info import MetricInfo
from app.repositories.qdrant.metric_qdrant_repository import (
    MetricQdrantRepository,
)


def test_collection_name_comes_from_rebuild_config() -> None:
    assert (
        MetricQdrantRepository.collection_name
        == app_config.qdrant.metric_collection_name
    )


async def test_ensure_collection_skips_creation_when_collection_exists() -> None:
    """指标集合已经存在时，不应重复创建。"""

    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = True
    repository = MetricQdrantRepository(client)

    await repository.ensure_collection()

    client.collection_exists.assert_awaited_once_with(repository.collection_name)
    client.create_collection.assert_not_awaited()


async def test_ensure_collection_creates_missing_collection() -> None:
    """指标集合不存在时，按 Embedding 维度和余弦距离创建。"""

    client = AsyncMock(spec=AsyncQdrantClient)
    client.collection_exists.return_value = False
    repository = MetricQdrantRepository(client)

    await repository.ensure_collection()

    client.create_collection.assert_awaited_once()
    arguments = client.create_collection.await_args.kwargs
    vector_params = arguments["vectors_config"]
    assert arguments["collection_name"] == repository.collection_name
    assert vector_params.size == app_config.qdrant.embedding_size
    assert vector_params.distance == Distance.COSINE


async def test_upsert_builds_points_and_writes_them_in_batches() -> None:
    """指标 id、向量和 payload 会组成 Point，并分批写入。"""

    client = AsyncMock(spec=AsyncQdrantClient)
    repository = MetricQdrantRepository(client)
    ids = [
        "550e8400-e29b-41d4-a716-446655440011",
        "550e8400-e29b-41d4-a716-446655440012",
        "550e8400-e29b-41d4-a716-446655440013",
    ]
    embeddings = [
        [0.1, 0.2],
        [0.3, 0.4],
        [0.5, 0.6],
    ]
    payloads = [
        {"id": "GMV", "name": "GMV"},
        {"id": "AOV", "name": "AOV"},
        {"id": "ORDER_COUNT", "name": "ORDER_COUNT"},
    ]

    await repository.upsert(ids, embeddings, payloads, batch_size=2)

    assert client.upsert.await_count == 2
    first_points = client.upsert.await_args_list[0].kwargs["points"]
    second_points = client.upsert.await_args_list[1].kwargs["points"]
    assert [str(point.id) for point in first_points] == ids[:2]
    assert [point.vector for point in first_points] == embeddings[:2]
    assert [point.payload for point in first_points] == payloads[:2]
    assert [str(point.id) for point in second_points] == ids[2:]
    assert [point.vector for point in second_points] == embeddings[2:]
    assert [point.payload for point in second_points] == payloads[2:]
    assert client.upsert.await_args_list == [
        call(collection_name=repository.collection_name, points=first_points),
        call(collection_name=repository.collection_name, points=second_points),
    ]


async def test_search_queries_qdrant_and_returns_metric_entities() -> None:
    """Qdrant 返回的指标 payload 会被还原成 MetricInfo。"""

    client = AsyncMock(spec=AsyncQdrantClient)
    result = Mock()
    result.points = [
        Mock(
            payload={
                "id": "GMV",
                "name": "GMV",
                "description": "所有订单成交金额总和。",
                "relevant_columns": ["fact_order.order_amount"],
                "alias": ["成交总额", "订单总额"],
            }
        )
    ]
    client.query_points.return_value = result
    repository = MetricQdrantRepository(client)
    embedding = [0.1, 0.2, 0.3]

    metrics = await repository.search(
        embedding,
        score_threshold=0.7,
        limit=5,
    )

    assert metrics == [
        MetricInfo(
            id="GMV",
            name="GMV",
            description="所有订单成交金额总和。",
            relevant_columns=["fact_order.order_amount"],
            alias=["成交总额", "订单总额"],
        )
    ]
    client.query_points.assert_awaited_once_with(
        collection_name=repository.collection_name,
        query=embedding,
        limit=5,
        score_threshold=0.7,
    )


async def test_search_returns_empty_list_when_qdrant_has_no_matches() -> None:
    """Qdrant 没有召回指标时返回空列表。"""

    client = AsyncMock(spec=AsyncQdrantClient)
    result = Mock()
    result.points = []
    client.query_points.return_value = result
    repository = MetricQdrantRepository(client)

    metrics = await repository.search([0.1, 0.2])

    assert metrics == []
