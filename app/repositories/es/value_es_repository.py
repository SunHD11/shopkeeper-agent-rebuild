"""
字段真实取值 Elasticsearch Repository。

这个 Repository 负责：

1. 创建用于保存字段真实值的 Elasticsearch 索引；
2. 将 ValueInfo 实体分批写入 Elasticsearch；
3. 根据用户输入搜索真实字段值；
4. 把 Elasticsearch 返回结果转换回 ValueInfo 实体。

它不负责从 DW MySQL 读取数据，也不负责创建 ValueInfo。
这些工作由 DWMySQLRepository 和 Service 层完成。
"""

# asdict() 可以把 dataclass 对象转换成普通字典。
#
# 例如：
#
# ValueInfo(
#     id="dim_region.region_name.华东",
#     value="华东",
#     column_id="dim_region.region_name",
# )
#
# 转换后：
#
# {
#     "id": "dim_region.region_name.华东",
#     "value": "华东",
#     "column_id": "dim_region.region_name",
# }
from dataclasses import asdict

# AsyncElasticsearch 是 Elasticsearch 官方提供的异步客户端。
#
# 因为创建索引、批量写入和查询都是网络操作，
# 所以这里使用异步客户端，后面的方法也都使用 async/await。
from elasticsearch import AsyncElasticsearch

# app_config.es.index_name 保存当前项目应该使用的 Elasticsearch 索引名称。
# rebuild 配置为 value_index_rebuild，从而与原项目的 value_index 相互隔离。
from app.conf.app_config import app_config

# ValueInfo 是项目内部表示“字段真实取值”的业务实体。
#
# Repository 对外接收和返回 ValueInfo，
# 从而避免 Service 层直接依赖 Elasticsearch 的数据格式。
from app.entities.value_info import ValueInfo


class ValueESRepository:
    """
    负责字段真实取值在 Elasticsearch 中的创建、写入和查询。

    例如：

    “华东”属于 dim_region.region_name
    “黄金会员”属于 dim_customer.level_name
    “已支付”属于 fact_order.order_status
    """

    # 定义 Elasticsearch 索引中每个字段的类型。
    #
    # 这类似于 MySQL 的建表结构，但 Elasticsearch 使用 mapping。
    index_mappings = {
        # 禁止 Elasticsearch 根据未知字段自动生成 Mapping。
        #
        # 如果文档里出现 Mapping 没有声明的字段，
        # 这些字段不会被自动建立为可检索字段。
        "dynamic": False,
        "properties": {
            # ValueInfo.id 是文档的业务唯一标识。
            #
            # keyword 不会进行分词，适合：
            # - 精确匹配
            # - 排序
            # - 聚合
            "id": {
                "type": "keyword",
            },
            # value 保存字段的真实业务值，例如：
            # 华东、广东省、黄金会员、已支付。
            #
            # text 类型会进行分词，因此适合全文检索。
            "value": {
                "type": "text",
                # 写入文档时使用 IK 最细粒度分词。
                #
                # 例如：
                # “广东省深圳市”
                #
                # 可能拆分成：
                # 广东省、广东、深圳市、深圳等词语。
                "analyzer": "ik_max_word",
                # 用户搜索时同样使用 IK 分词。
                "search_analyzer": "ik_max_word",
            },
            # column_id 表示这个业务值属于哪个字段。
            #
            # 例如：
            # “华东”属于 dim_region.region_name。
            #
            # column_id 需要完整精确匹配，因此使用 keyword。
            "column_id": {
                "type": "keyword",
            },
        },
    }

    def __init__(
        self,
        client: AsyncElasticsearch,
        index_name: str | None = None,
    ):
        """
        接收外部创建好的 Elasticsearch 异步客户端。

        参数：
            client：
                已经初始化的 AsyncElasticsearch。

            index_name：
                当前 Repository 操作的 Elasticsearch 索引名称。

                没有显式传入时，默认读取 app_config.es.index_name；
                rebuild 因此使用 value_index_rebuild，不会误读写原项目的
                value_index。测试或其他隔离环境仍然可以传入自定义名称。

        Repository 不负责创建和关闭 Client，
        它只使用传入的 Client 操作 Elasticsearch。
        """

        # 保存成实例属性。
        #
        # 后面的 ensure_index()、index() 和 search()
        # 都通过 self.client 使用同一个 Elasticsearch 客户端。
        self.client = client

        # 不能继续把 value_index 硬编码成类属性，否则原项目和 rebuild 即使连接
        # 不同端口，也可能在配置调整或共享 ES 时访问同名索引。
        #
        # `is not None` 而不是 `or`，可以让空字符串等非法值继续暴露给 ES，
        # 避免 Repository 悄悄替调用方改回默认值，掩盖上游配置错误。
        self.index_name = (
            index_name if index_name is not None else app_config.es.index_name
        )

    async def ensure_index(self):
        """
        确保当前项目配置的字段值索引存在。

        如果索引已经存在：
            不执行创建操作。

        如果索引不存在：
            使用 index_mappings 创建索引。

        这个方法可以让元数据构建流程重复执行，
        不会因为索引已经存在而创建失败。
        """

        # client.indices 用于执行 Elasticsearch 索引级别的操作。
        #
        # exists() 查询指定索引是否已经存在。
        index_exists = await self.client.indices.exists(
            index=self.index_name,
        )

        # 只有索引不存在时才创建。
        if not index_exists:
            await self.client.indices.create(
                # 创建的索引名称。
                index=self.index_name,
                # 使用类中定义的字段 Mapping。
                mappings=self.index_mappings,
            )

    async def index(
        self,
        value_infos: list[ValueInfo],
        batch_size: int = 20,
    ):
        """
        将字段真实值分批写入 Elasticsearch。

        参数：
            value_infos：
                等待写入的 ValueInfo 实体列表。

            batch_size：
                每批最多写入多少个 ValueInfo，默认是 20。

        Elasticsearch Bulk API 要求操作指令和文档内容交替出现。
        """

        # 如果没有任何数据，直接结束。
        #
        # 这样可以避免向 Elasticsearch 发送一次没有意义的空请求。
        if not value_infos:
            return

        # 按照 batch_size 对 ValueInfo 进行分批。
        #
        # 假设一共有 45 条数据，batch_size=20：
        #
        # 第一批：value_infos[0:20]
        # 第二批：value_infos[20:40]
        # 第三批：value_infos[40:60]
        for i in range(
            0,
            len(value_infos),
            batch_size,
        ):
            # 获取当前批次的数据。
            batch = value_infos[i : i + batch_size]

            # 保存当前批次对应的 Elasticsearch Bulk 操作。
            #
            # Bulk API 的数据格式是：
            #
            # [
            #     操作说明,
            #     文档内容,
            #     操作说明,
            #     文档内容,
            # ]
            batch_operations = []

            for value_info in batch:
                # 第一部分：告诉 Elasticsearch 要执行什么操作。
                #
                # 这里使用 index：
                # - 文档不存在时创建；
                # - 文档已经存在时覆盖。
                #
                # _id 使用 ValueInfo.id，
                # 因此重复构建知识库时不会产生同 ID 的重复文档。
                batch_operations.append(
                    {
                        "index": {
                            "_index": self.index_name,
                            "_id": value_info.id,
                        }
                    }
                )

                # 第二部分：真正要写入的文档内容。
                #
                # ValueInfo 是 dataclass，
                # asdict() 将它转换成 Elasticsearch 可以接收的普通字典。
                batch_operations.append(asdict(value_info))

            # 将当前批次一次性写入 Elasticsearch。
            #
            # bulk() 是网络操作，因此需要 await。
            await self.client.bulk(
                operations=batch_operations,
            )

    async def search(
        self,
        keyword: str,
        score_threshold: float = 0.6,
        limit: int = 20,
    ) -> list[ValueInfo]:
        """
        根据关键词搜索字段真实值。

        参数：
            keyword：
                用户问题中可能出现的业务值，例如“华东”。

            score_threshold：
                Elasticsearch 最低相关性分数。
                低于这个分数的结果不会返回。

            limit：
                最多返回多少条结果，默认 20。

        返回：
            ValueInfo 业务实体列表。
        """

        # 在 value 字段上执行 match 查询。
        #
        # match 查询会使用 Mapping 中配置的分词器，
        # 因此适合查询中文业务词。
        response = await self.client.search(
            # 指定查询哪个索引。
            index=self.index_name,
            # 搜索 value 字段。
            query={
                "match": {
                    "value": keyword,
                }
            },
            # 限制最多返回多少条结果。
            size=limit,
            # 过滤掉相关性分数过低的结果。
            min_score=score_threshold,
        )

        # Elasticsearch 返回结构大致如下：
        #
        # {
        #     "hits": {
        #         "hits": [
        #             {
        #                 "_id": "...",
        #                 "_score": 1.2,
        #                 "_source": {
        #                     "id": "...",
        #                     "value": "华东",
        #                     "column_id": "dim_region.region_name",
        #                 },
        #             }
        #         ]
        #     }
        # }
        #
        # 真正的业务文档保存在每个 hit 的 _source 中。
        #
        # ValueInfo(**hit["_source"]) 相当于：
        #
        # ValueInfo(
        #     id=hit["_source"]["id"],
        #     value=hit["_source"]["value"],
        #     column_id=hit["_source"]["column_id"],
        # )
        return [ValueInfo(**hit["_source"]) for hit in response["hits"]["hits"]]
