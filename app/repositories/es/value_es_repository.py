"""
字段真实取值 Elasticsearch Repository。

负责创建字段值索引、批量写入 ValueInfo，
以及把 Elasticsearch 的搜索结果还原成业务实体。

DW Repository 负责读取真实值，Service 负责组装 ValueInfo，
本 Repository 只关心这些值如何写入和查询。
"""

from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.entities.value_info import ValueInfo


class ValueESRepository:
    """负责字段真实取值索引的创建、写入和查询。"""

    # 所有字段真实值统一保存在这个索引中。
    index_name = "value_index"

    # Elasticsearch Mapping 用来声明文档字段如何建立索引。
    index_mappings = {
        # 未声明字段不会被 Elasticsearch 自动建立为可检索字段。
        "dynamic": False,
        "properties": {
            # 业务唯一标识需要精确匹配，因此使用 keyword。
            "id": {"type": "keyword"},
            # 真实字段值需要支持中文检索，因此使用 text 和 IK 分词器。
            "value": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_max_word",
            },
            # 所属字段 id 需要精确匹配，因此使用 keyword。
            "column_id": {"type": "keyword"},
        },
    }

    def __init__(self, client: AsyncElasticsearch):
        """接收由客户端管理器创建的异步 Elasticsearch Client。"""
        self.client = client

    async def ensure_index(self):
        """确保字段真实值索引存在，不存在时按 Mapping 创建。"""
        if not await self.client.indices.exists(index=self.index_name):
            await self.client.indices.create(
                index=self.index_name,
                mappings=self.index_mappings,
            )

    async def index(
        self,
        value_infos: list[ValueInfo],
        batch_size: int = 20,
    ):
        """把 ValueInfo 按 batch_size 分批写入 Elasticsearch。"""
        # 空列表不需要向 Elasticsearch 发送 Bulk 请求。
        if not value_infos:
            return

        for i in range(0, len(value_infos), batch_size):
            batch = value_infos[i : i + batch_size]
            batch_operations = []

            for value_info in batch:
                # Bulk API 要求每份文档前面先放一条操作描述。
                # 使用稳定的 ValueInfo.id 作为 ES _id，重复构建时会覆盖同一文档。
                batch_operations.append(
                    {
                        "index": {
                            "_index": self.index_name,
                            "_id": value_info.id,
                        }
                    }
                )

                # ValueInfo 是 dataclass，asdict() 将其转换为普通字典。
                batch_operations.append(asdict(value_info))

            await self.client.bulk(operations=batch_operations)

    async def search(
        self,
        keyword: str,
        score_threshold: float = 0.6,
        limit: int = 20,
    ) -> list[ValueInfo]:
        """按关键词检索字段真实值，并还原成 ValueInfo 实体。"""
        response = await self.client.search(
            index=self.index_name,
            query={"match": {"value": keyword}},
            size=limit,
            min_score=score_threshold,
        )

        # Elasticsearch 的业务文档保存在每条命中的 _source 中。
        return [ValueInfo(**hit["_source"]) for hit in response["hits"]["hits"]]
