"""
字段向量 Repository。

负责管理字段向量集合，并将 Service 准备好的向量 Point
批量写入 Qdrant。

Service 层负责：
- 决定一个字段拆成哪些检索文本；
- 调用 Embedding 服务生成向量；
- 准备 Point 的 ID 和 payload。

Repository 负责：
- 确保 Collection 存在；
- 将向量 Point 分批写入；
- 根据向量检索字段；
- 将 Qdrant payload 还原成 ColumnInfo。
"""

# AsyncQdrantClient 是 Qdrant 的异步客户端。
#
# 它由 QdrantClientManager 创建，
# 再通过构造方法注入 Repository。
from qdrant_client import AsyncQdrantClient

# PointStruct 表示 Qdrant 中的一个向量点。
#
# 每个 Point 包含：
# - id：向量点唯一标识；
# - vector：Embedding 向量；
# - payload：字段完整业务信息。
from qdrant_client.http.models import PointStruct

# Distance 决定向量之间如何计算距离。
# VectorParams 用于声明 Collection 的向量维度和距离算法。
from qdrant_client.models import Distance, VectorParams

# embedding_size 来自项目配置。
#
# Qdrant Collection 的向量维度，
# 必须和 Embedding 模型输出维度完全一致。
from app.conf.app_config import app_config

# search() 最终会把 Qdrant payload 还原成 ColumnInfo。
from app.entities.column_info import ColumnInfo


class ColumnQdrantRepository:
    """
    负责字段向量集合的创建、写入和检索。

    它不生成 Embedding，只接收已经生成好的向量。
    """

    # 字段元数据使用独立 Collection。
    #
    # 指标元数据后面会使用：
    # metric_info_collection
    #
    # 字段和指标分开存储，可以避免搜索结果类型混杂。
    collection_name = "column_info_collection"

    def __init__(
        self,
        client: AsyncQdrantClient,
    ):
        """
        接收外部创建的异步 Qdrant Client。

        参数：
            client：已经初始化的 AsyncQdrantClient。

        Repository 不负责创建或关闭 Client。
        """

        self.client = client

    async def ensure_collection(self):
        """
        确保字段向量 Collection 存在。

        如果 Collection 已存在：
            不执行任何创建操作。

        如果 Collection 不存在：
            根据 Embedding 维度和 COSINE 距离创建。
        """

        # 向 Qdrant 查询指定 Collection 是否存在。
        exists = await self.client.collection_exists(self.collection_name)

        # 只有 Collection 不存在时才创建。
        #
        # 这样重复执行元数据构建脚本时，
        # 不会因为 Collection 已存在而创建失败。
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    # 向量维度必须与 Embedding 输出一致。
                    #
                    # 假设 Embedding 输出：
                    # [0.1, 0.2, ..., 0.8]
                    #
                    # 一共有 1024 个数字，
                    # 那么 embedding_size 必须是 1024。
                    size=app_config.qdrant.embedding_size,
                    # 使用余弦距离计算语义相似度。
                    #
                    # 它更关注两个向量的方向是否接近，
                    # 常用于文本 Embedding 检索。
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
        将字段向量点分批写入 Qdrant。

        参数：
            ids：
                每个向量点的唯一 ID。

            embeddings：
                每个检索文本对应的向量。

            payloads：
                每个向量点携带的完整字段元数据。

            batch_size：
                每批最多写入多少个 Point，默认 10。

        三个列表必须按照相同下标一一对应：

            ids[0]
            embeddings[0]
            payloads[0]

        共同组成第一个 Point。
        """

        # zip() 按照相同位置组合三个列表。
        #
        # 例如：
        #
        # id = "point-1"
        # embedding = [0.1, 0.2, 0.3]
        # payload = {
        #     "id": "fact_order.order_amount",
        #     "name": "order_amount",
        #     ...
        # }
        #
        # 会组成：
        #
        # PointStruct(
        #     id="point-1",
        #     vector=[0.1, 0.2, 0.3],
        #     payload={...},
        # )
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

        # 将所有 Point 按 batch_size 分批。
        #
        # 假设共有 25 个 Point，batch_size=10：
        #
        # 第一批：points[0:10]
        # 第二批：points[10:20]
        # 第三批：points[20:30]
        for i in range(
            0,
            len(points),
            batch_size,
        ):
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points[i : i + batch_size],
            )

    async def search(
        self,
        embedding: list[float],
        score_threshold: float = 0.6,
        limit: int = 20,
    ) -> list[ColumnInfo]:
        """
        根据问题向量检索最相似的字段元数据。

        参数：
            embedding：
                用户问题或关键词对应的 Embedding。

            score_threshold：
                最低相似度分数，默认 0.6。
                低于这个分数的结果不会返回。

            limit：
                最多返回多少个字段，默认 20。

        返回：
            ColumnInfo 业务实体列表。
        """

        # query_points() 会在字段 Collection 中，
        # 查询和 embedding 最相似的向量点。
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
        )

        # Qdrant 中保存的是：
        #
        # Point
        # ├── id
        # ├── vector
        # ├── score
        # └── payload
        #
        # payload 中保存的是完整 ColumnInfo 字段：
        #
        # {
        #     "id": "fact_order.order_amount",
        #     "name": "order_amount",
        #     "type": "decimal(10,2)",
        #     "role": "measure",
        #     "examples": [100, 200],
        #     "description": "订单金额",
        #     "alias": ["销售额", "收入"],
        #     "table_id": "fact_order",
        # }
        #
        # Repository 将 payload 转回 ColumnInfo，
        # 让 Service 不依赖 Qdrant Point 类型。
        return [ColumnInfo(**point.payload) for point in result.points]
