"""
指标向量 Repository。

负责管理指标向量集合，并将 Service 层准备好的指标向量点
批量写入 Qdrant。

Service 层负责：
- 决定每个指标要生成哪些检索文本；
- 调用 Embedding 服务把文本转换成向量；
- 准备向量点的 id 和 payload。

Repository 负责：
- 确保指标 Collection 存在；
- 将向量点分批写入 Qdrant；
- 根据问题向量检索指标；
- 将 Qdrant payload 还原成 MetricInfo。
"""

# AsyncQdrantClient 是 Qdrant 的异步客户端。
#
# Client 由项目中的 QdrantClientManager 创建，
# 然后通过构造方法注入当前 Repository。
from qdrant_client import AsyncQdrantClient

# PointStruct 表示 Qdrant 中的一条向量记录。
#
# 每个 Point 主要包含：
# - id：当前向量点的唯一标识；
# - vector：Embedding 生成的浮点数向量；
# - payload：完整的指标业务信息。
#
# Distance 用来指定向量距离计算方式。
# VectorParams 用来声明 Collection 的向量维度和距离算法。
from qdrant_client.models import Distance, PointStruct, VectorParams

# app_config.qdrant.embedding_size 保存 Embedding 模型的输出维度。
# Qdrant Collection 的向量维度必须和模型输出维度完全一致。
from app.conf.app_config import app_config

# search() 会把 Qdrant payload 转换成 MetricInfo 业务实体。
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    """
    负责指标向量集合的创建、写入和检索。

    字段和指标虽然都使用 Qdrant，但它们属于不同业务对象，
    因此分别保存在不同 Collection 中，避免搜索结果相互混杂。
    """

    # 指标元数据使用独立的 Collection。
    #
    # 字段元数据使用：column_info_collection
    # 指标元数据使用：metric_info_collection
    collection_name = "metric_info_collection"

    def __init__(
        self,
        client: AsyncQdrantClient,
    ):
        """
        接收外部创建的异步 Qdrant Client。

        Repository 不负责创建或关闭 Client，
        只保存并使用传入的 Client。
        """
        self.client = client

    async def ensure_collection(self):
        """
        确保指标向量 Collection 已经存在。

        如果 Collection 已存在：
            不执行任何创建操作。

        如果 Collection 不存在：
            按照 Embedding 输出维度和余弦距离创建。
        """

        # 查询 Qdrant 中是否已经存在指标 Collection。
        collection_exists = await self.client.collection_exists(self.collection_name)

        # 只有集合不存在时才创建。
        # 这使得知识库构建任务可以重复运行。
        if not collection_exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    # 向量维度来自统一配置。
                    #
                    # 假设 Embedding 模型输出 1024 个浮点数，
                    # 这里的 size 也必须是 1024，否则写入会失败。
                    size=app_config.qdrant.embedding_size,
                    # 使用余弦距离比较文本向量的语义方向。
                    # 两段文本含义越接近，对应向量的相似度通常越高。
                    distance=Distance.COSINE,
                ),
            )

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict],
        batch_size: int = 10,
    ):
        """
        将指标向量点分批写入 Qdrant。

        参数：
            ids：
                每个向量点的唯一 ID。

            embeddings：
                指标检索文本对应的 Embedding 向量。

            payloads：
                每个向量点携带的完整指标元数据。

            batch_size：
                每批最多写入多少个 Point，默认是 10。

        三个列表通过相同下标一一对应：

            ids[0] + embeddings[0] + payloads[0]

        共同组成第一个 Qdrant Point。
        """

        # zip() 会把三个列表中相同位置的元素组合起来。
        #
        # 例如：
        # id = "550e8400-e29b-41d4-a716-446655440001"
        # embedding = [0.1, 0.2, 0.3]
        # payload = {
        #     "id": "GMV",
        #     "name": "GMV",
        #     "description": "所有订单成交金额总和",
        #     "relevant_columns": ["fact_order.order_amount"],
        #     "alias": ["成交总额", "订单总额"],
        # }
        #
        # 最终会组成一个 PointStruct。
        points: list[PointStruct] = [
            PointStruct(
                id=id,
                vector=embedding,
                payload=payload,
            )
            for id, embedding, payload in zip(
                ids,
                embeddings,
                payloads,
            )
        ]

        # 按照 batch_size 对 Point 进行分批写入。
        #
        # 假设共有 25 个 Point，batch_size=10：
        # 第一批：points[0:10]
        # 第二批：points[10:20]
        # 第三批：points[20:30]
        for i in range(0, len(points), batch_size):
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points[i : i + batch_size],
            )

    async def search(
        self,
        embedding: list[float],
        score_threshold: float = 0.6,
        limit: int = 20,
    ) -> list[MetricInfo]:
        """
        根据问题向量检索最相似的指标。

        参数：
            embedding：
                用户问题或指标关键词生成的 Embedding。

            score_threshold：
                最低向量相似度，默认是 0.6。

            limit：
                最多返回多少个指标，默认是 20。

        返回：
            MetricInfo 业务实体列表。
        """

        # 在指标 Collection 中查询与问题向量最接近的 Point。
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
        )

        # Qdrant 的返回结果中，每个 Point 的 payload 保存完整指标信息。
        #
        # 例如：
        # {
        #     "id": "GMV",
        #     "name": "GMV",
        #     "description": "所有订单成交金额总和",
        #     "relevant_columns": ["fact_order.order_amount"],
        #     "alias": ["成交总额", "订单总额"],
        # }
        #
        # Repository 将 payload 还原为 MetricInfo，
        # 这样 Service 层不需要依赖 Qdrant 的 Point 类型。
        return [MetricInfo(**point.payload) for point in result.points]
