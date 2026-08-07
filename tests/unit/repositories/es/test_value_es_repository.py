"""测试字段真实取值 Elasticsearch Repository 的索引、写入和查询。"""

from unittest.mock import AsyncMock, Mock

from elasticsearch import AsyncElasticsearch

from app.conf.app_config import app_config
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository


def create_es_client() -> Mock:
    """创建只用于单元测试的异步 Elasticsearch Client。"""
    client = Mock(spec=AsyncElasticsearch)
    client.indices = Mock()
    client.indices.exists = AsyncMock()
    client.indices.create = AsyncMock()
    client.bulk = AsyncMock()
    client.search = AsyncMock()
    return client


def test_repository_uses_rebuild_index_name_by_default() -> None:
    """未显式传入索引名时，应使用 rebuild 配置中的独立索引。"""

    repository = ValueESRepository(create_es_client())

    # 这条断言同时保护两层契约：
    # 1. Repository 必须从 AppConfig 读取索引名称；
    # 2. rebuild 的 YAML 必须继续使用带 _rebuild 后缀的隔离索引。
    assert repository.index_name == app_config.es.index_name
    assert repository.index_name == "value_index_rebuild"


def test_repository_allows_explicit_index_name_override() -> None:
    """测试或其他隔离环境可以通过构造参数覆盖默认索引名称。"""

    repository = ValueESRepository(
        create_es_client(),
        index_name="value_index_test",
    )

    assert repository.index_name == "value_index_test"


async def test_ensure_index_skips_creation_when_index_exists() -> None:
    """value_index 已存在时不应重复创建。"""
    client = create_es_client()
    client.indices.exists.return_value = True
    repository = ValueESRepository(client)

    await repository.ensure_index()

    client.indices.exists.assert_awaited_once_with(index=repository.index_name)
    client.indices.create.assert_not_awaited()


async def test_ensure_index_creates_missing_index() -> None:
    """value_index 不存在时应使用预定义 Mapping 创建。"""
    client = create_es_client()
    client.indices.exists.return_value = False
    repository = ValueESRepository(client)

    await repository.ensure_index()

    client.indices.create.assert_awaited_once_with(
        index=repository.index_name,
        mappings=repository.index_mappings,
    )


async def test_index_skips_bulk_request_for_empty_values() -> None:
    """没有字段真实值时，不应发送空的 Bulk 请求。"""
    client = create_es_client()
    repository = ValueESRepository(client)

    await repository.index([])

    client.bulk.assert_not_awaited()


async def test_index_writes_value_infos_in_batches() -> None:
    """ValueInfo 会转换成 Bulk Operations 并按照批次写入。"""
    client = create_es_client()
    repository = ValueESRepository(client)
    value_infos = [
        ValueInfo(
            id="dim_region.region_name.华东",
            value="华东",
            column_id="dim_region.region_name",
        ),
        ValueInfo(
            id="dim_region.region_name.华南",
            value="华南",
            column_id="dim_region.region_name",
        ),
        ValueInfo(
            id="dim_customer.level_name.黄金会员",
            value="黄金会员",
            column_id="dim_customer.level_name",
        ),
    ]

    await repository.index(value_infos, batch_size=2)

    assert client.bulk.await_count == 2
    first_operations = client.bulk.await_args_list[0].kwargs["operations"]
    second_operations = client.bulk.await_args_list[1].kwargs["operations"]
    assert first_operations == [
        {
            "index": {
                "_index": repository.index_name,
                "_id": "dim_region.region_name.华东",
            }
        },
        {
            "id": "dim_region.region_name.华东",
            "value": "华东",
            "column_id": "dim_region.region_name",
        },
        {
            "index": {
                "_index": repository.index_name,
                "_id": "dim_region.region_name.华南",
            }
        },
        {
            "id": "dim_region.region_name.华南",
            "value": "华南",
            "column_id": "dim_region.region_name",
        },
    ]
    assert second_operations == [
        {
            "index": {
                "_index": repository.index_name,
                "_id": "dim_customer.level_name.黄金会员",
            }
        },
        {
            "id": "dim_customer.level_name.黄金会员",
            "value": "黄金会员",
            "column_id": "dim_customer.level_name",
        },
    ]


async def test_search_returns_value_info_entities() -> None:
    """命中的 _source 会转换成 ValueInfo 业务实体。"""
    client = create_es_client()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "id": "dim_region.region_name.华东",
                        "value": "华东",
                        "column_id": "dim_region.region_name",
                    }
                }
            ]
        }
    }
    repository = ValueESRepository(client)

    values = await repository.search(
        "华东",
        score_threshold=0.8,
        limit=5,
    )

    assert values == [
        ValueInfo(
            id="dim_region.region_name.华东",
            value="华东",
            column_id="dim_region.region_name",
        )
    ]
    client.search.assert_awaited_once_with(
        index=repository.index_name,
        query={"match": {"value": "华东"}},
        size=5,
        min_score=0.8,
    )


async def test_search_returns_empty_list_when_no_value_matches() -> None:
    """没有匹配的字段真实值时返回空列表。"""
    client = create_es_client()
    client.search.return_value = {"hits": {"hits": []}}
    repository = ValueESRepository(client)

    values = await repository.search("不存在的业务值")

    assert values == []
