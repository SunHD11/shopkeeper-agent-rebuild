"""
元数据知识库构建服务。

这个 Service 位于脚本入口和 Repository 之间，负责组织完整业务流程：

1. 读取 meta_config.yaml 中人工维护的业务语义；
2. 从 DW MySQL 补充真实字段类型和字段值；
3. 把结构化元数据写入 Meta MySQL；
4. 把字段和指标文本向量化后写入 Qdrant；
5. 把允许同步的字段真实值写入 Elasticsearch。

Service 只决定“先做什么、后做什么以及数据如何组合”，
具体数据库读写操作仍然交给各个 Repository。
"""

# uuid5() 根据业务对象和文本槽位生成稳定 Qdrant Point ID。
# 相同配置重复构建时会覆盖已有 Point，而不是不断产生重复向量。
import uuid

# asdict() 把 dataclass 业务实体转换成普通字典，作为 Qdrant payload。
from dataclasses import asdict

# Path 用来表达外部传入的 meta_config.yaml 路径。
from pathlib import Path

# HuggingFaceEndpointEmbeddings 提供异步文本向量化方法 aembed_documents()。
from langchain_huggingface import HuggingFaceEndpointEmbeddings

# OmegaConf 负责读取 YAML，并按照 MetaConfig dataclass 结构完成转换。
from omegaconf import OmegaConf

from app.conf.meta_config import MetaConfig
from app.core.log import logger
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


class MetaKnowledgeService:
    """
    串联元数据知识库构建流程的应用服务。

    可以把这一层理解成“总装车间”：

    - YAML 提供人工维护的业务含义；
    - DW MySQL 提供真实字段结构和真实数据；
    - Meta MySQL 保存权威的结构化元数据；
    - Qdrant 保存字段和指标的语义向量；
    - Elasticsearch 保存可以通过关键词检索的真实业务值。
    """

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        value_es_repository: ValueESRepository,
        metric_qdrant_repository: MetricQdrantRepository,
    ):
        """
        通过构造方法接收完整构建流程所需的依赖。

        Service 不负责创建连接和 Repository。外部脚本创建好这些对象后，
        再把它们注入进来。这样既能明确各层职责，也方便单元测试传入 Mock。
        """

        # 保存表、字段、指标以及指标字段关系。
        self.meta_mysql_repository = meta_mysql_repository

        # 查询 DW 中的真实字段类型、示例值和待同步真实值。
        self.dw_mysql_repository = dw_mysql_repository

        # 管理 column_info_collection 中的字段向量。
        self.column_qdrant_repository = column_qdrant_repository

        # 把字段和指标的检索文本转换成 Embedding 向量。
        self.embedding_client = embedding_client

        # 管理 Elasticsearch value_index 中的字段真实值。
        self.value_es_repository = value_es_repository

        # 管理 metric_info_collection 中的指标向量。
        self.metric_qdrant_repository = metric_qdrant_repository

    async def _save_tables_to_meta_db(
        self,
        meta_config: MetaConfig,
    ) -> list[ColumnInfo]:
        """
        融合 YAML 业务配置和 DW 技术事实，并写入 Meta MySQL。

        输入：
            meta_config.tables 中的表和字段配置。

        数据补充：
            从 DW MySQL 查询字段真实类型和少量真实示例值。

        输出：
            写入 table_info、column_info，并返回全部 ColumnInfo，
            供后面的 Qdrant 和 Elasticsearch 构建步骤继续使用。
        """

        # 先在内存中准备完整实体列表，再统一开启事务保存。
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        # build() 只有在 meta_config.tables 非空时才调用这个方法。
        # 因此这里按照原项目流程直接遍历表配置。
        for table in meta_config.tables or []:
            # 表 id 直接使用 DW 中的真实表名。
            table_info = TableInfo(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description,
            )
            table_infos.append(table_info)

            # 字段类型属于数据库技术事实，不能只依赖人工 YAML。
            # 返回示例：
            # {
            #     "order_id": "varchar(64)",
            #     "order_amount": "decimal(10,2)",
            # }
            column_types = await self.dw_mysql_repository.get_column_types(table.name)

            for column in table.columns:
                # 读取少量 distinct 示例值，帮助后续模型理解字段内容。
                # 这里使用 Repository 的默认 limit，而不是同步 ES 时的 100000。
                column_values = await self.dw_mysql_repository.get_column_values(
                    table.name,
                    column.name,
                )

                # ColumnInfo 同时包含：
                # - YAML 中的业务语义；
                # - DW 中的真实字段类型和示例值。
                column_info = ColumnInfo(
                    # 使用“表名.字段名”避免不同表出现同名字段冲突。
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types[column.name],
                    role=column.role,
                    examples=column_values,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name,
                )
                column_infos.append(column_info)

        # 表和字段放入同一笔事务。
        # 任一步保存失败，事务都会回滚，避免产生半成品数据。
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_table_infos(table_infos)
            await self.meta_mysql_repository.save_column_infos(column_infos)

        # 后续字段向量和字段值索引都继续使用这份完整字段实体。
        return column_infos

    async def _save_column_info_to_qdrant(
        self,
        column_infos: list[ColumnInfo],
    ):
        """
        为字段名、字段描述和字段别名建立 Qdrant 向量索引。

        同一个字段会对应多个向量 Point，但所有 Point 的 payload 都保存
        同一个完整 ColumnInfo。这样用户无论命中字段名、描述还是别名，
        最终都能得到相同字段业务实体。
        """

        # Qdrant Collection 不存在时由 Repository 创建。
        await self.column_qdrant_repository.ensure_collection()

        # 每个元素保存生成一个 Qdrant Point 所需的三部分信息。
        points: list[dict] = []

        for column_info in column_infos:
            # 入口一：字段真实名称，例如 order_amount。
            points.append(
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"shopkeeper:column:{column_info.id}:name",
                    ),
                    "embedding_text": column_info.name,
                    "payload": asdict(column_info),
                }
            )

            # 入口二：字段业务描述，例如“订单金额”。
            points.append(
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"shopkeeper:column:{column_info.id}:description",
                    ),
                    "embedding_text": column_info.description,
                    "payload": asdict(column_info),
                }
            )

            # 入口三：字段的每一个业务别名，例如“销售额”“收入”。
            for alias_index, alia in enumerate(column_info.alias):
                points.append(
                    {
                        "id": uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"shopkeeper:column:{column_info.id}:alias:{alias_index}",
                        ),
                        "embedding_text": alia,
                        "payload": asdict(column_info),
                    }
                )

        # 先单独抽出文本，并保持与 points 完全相同的顺序。
        embedding_texts = [point["embedding_text"] for point in points]

        # Embedding 服务每次最多处理 20 条，避免请求过大。
        embedding_batch_size = 20
        embeddings: list[list[float]] = []

        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]

            # aembed_documents() 异步返回与输入文本顺序一致的向量列表。
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        # 三个列表的相同下标必须表示同一个 Qdrant Point。
        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        # Repository 负责把三个列表组合成 PointStruct 并分批 upsert。
        await self.column_qdrant_repository.upsert(
            ids,
            embeddings,
            payloads,
        )

    async def _save_value_info_to_es(
        self,
        meta_config: MetaConfig,
        column_infos: list[ColumnInfo],
    ):
        """
        将 sync=True 字段的真实去重值写入 Elasticsearch。

        这条链路用于判断用户问题里的业务值属于哪个字段。例如搜索“华东”
        后，可以得到它属于 dim_region.region_name，而不是字段或指标名称。
        """

        # 确保 value_index 以及 IK 分词 Mapping 已经存在。
        await self.value_es_repository.ensure_index()

        # ColumnInfo 不保存 sync，因为 sync 是一次构建策略而不是字段业务属性。
        # 因此需要重新从 MetaConfig 建立字段 id 到 sync 的映射。
        column2sync: dict[str, bool] = {}

        for table in meta_config.tables or []:
            for column in table.columns:
                column_id = f"{table.name}.{column.name}"
                column2sync[column_id] = column.sync

        value_infos: list[ValueInfo] = []

        for column_info in column_infos:
            # 只同步 YAML 中明确设置 sync=True 的字段。
            if column2sync[column_info.id]:
                # 构建字段值索引需要尽可能覆盖枚举值，
                # 因此使用比 examples 更大的 limit。
                current_column_values = (
                    await self.dw_mysql_repository.get_column_values(
                        column_info.table_id,
                        column_info.name,
                        100000,
                    )
                )

                # 每个真实值都形成一份独立 ES 文档。
                current_value_infos = [
                    ValueInfo(
                        # 稳定 id 让同一字段值再次构建时覆盖原 ES 文档。
                        id=f"{column_info.id}.{current_column_value}",
                        value=current_column_value,
                        column_id=column_info.id,
                    )
                    for current_column_value in current_column_values
                ]
                value_infos.extend(current_value_infos)

        # Repository 内部会处理空列表并按照 batch_size 写入 Bulk API。
        await self.value_es_repository.index(value_infos)

    async def _save_metrics_to_meta_db(
        self,
        meta_config: MetaConfig,
    ) -> list[MetricInfo]:
        """
        将指标及其依赖字段关系写入 Meta MySQL。

        metric_info 保存指标本身，column_metric 保存指标和字段之间的关系。
        返回 MetricInfo 列表，供下一步建立指标向量索引。
        """

        metric_infos: list[MetricInfo] = []
        column_metrics: list[ColumnMetric] = []

        for metric in meta_config.metrics or []:
            # 当前项目直接使用指标名称作为业务 id，例如 GMV、AOV。
            metric_info = MetricInfo(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                alias=metric.alias,
            )
            metric_infos.append(metric_info)

            # 一个指标可能依赖一个或多个字段，因此逐个生成关系实体。
            for column_id in metric.relevant_columns:
                column_metric = ColumnMetric(
                    column_id=column_id,
                    metric_id=metric.name,
                )
                column_metrics.append(column_metric)

        # 指标本身和字段依赖关系必须在同一事务中保存。
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_metric_infos(metric_infos)
            await self.meta_mysql_repository.save_column_metrics(column_metrics)

        return metric_infos

    async def _save_metrics_to_qdrant(
        self,
        metric_infos: list[MetricInfo],
    ):
        """
        为指标名称、指标描述和指标别名建立 Qdrant 向量索引。

        它和字段向量链路结构相同，但写入独立的
        metric_info_collection，并在检索后还原成 MetricInfo。
        """

        await self.metric_qdrant_repository.ensure_collection()

        points: list[dict] = []

        for metric_info in metric_infos:
            # 入口一：指标标准名称，例如 GMV。
            points.append(
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"shopkeeper:metric:{metric_info.id}:name",
                    ),
                    "embedding_text": metric_info.name,
                    "payload": asdict(metric_info),
                }
            )

            # 入口二：指标业务描述。
            points.append(
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"shopkeeper:metric:{metric_info.id}:description",
                    ),
                    "embedding_text": metric_info.description,
                    "payload": asdict(metric_info),
                }
            )

            # 入口三：指标的每一个别名，例如“成交总额”。
            for alias_index, alia in enumerate(metric_info.alias):
                points.append(
                    {
                        "id": uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"shopkeeper:metric:{metric_info.id}:alias:{alias_index}",
                        ),
                        "embedding_text": alia,
                        "payload": asdict(metric_info),
                    }
                )

        embedding_texts = [point["embedding_text"] for point in points]
        embedding_batch_size = 20
        embeddings: list[list[float]] = []

        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        await self.metric_qdrant_repository.upsert(
            ids,
            embeddings,
            payloads,
        )

    async def build(self, config_path: Path):
        """
        读取配置并按照固定顺序构建整个元数据知识库。

        表字段链路：
            Meta MySQL -> 字段 Qdrant -> 字段值 Elasticsearch。

        指标链路：
            Meta MySQL -> 指标 Qdrant。

        tables 和 metrics 都允许为空，因此两条链路可以独立执行。
        """

        # 读取外部 YAML，得到尚未结构化的 DictConfig。
        context = OmegaConf.load(config_path)

        # 根据 MetaConfig dataclass 创建带默认值和类型结构的 Schema。
        schema = OmegaConf.structured(MetaConfig)

        # YAML 覆盖 Schema 中的默认值，再转换为普通 dataclass 对象。
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

        if meta_config.tables:
            # 第一步：生成 TableInfo、ColumnInfo 并写入 Meta MySQL。
            column_infos = await self._save_tables_to_meta_db(meta_config)
            logger.info("保存表信息和字段信息到 Meta MySQL")

            # 第二步：为字段名称、描述和别名建立向量索引。
            await self._save_column_info_to_qdrant(column_infos)
            logger.info("为字段信息建立向量索引")

            # 第三步：为 sync=True 字段的真实值建立全文索引。
            await self._save_value_info_to_es(meta_config, column_infos)
            logger.info("为字段取值建立全文索引")

        if meta_config.metrics:
            # 第四步：保存指标及指标字段关系。
            metric_infos = await self._save_metrics_to_meta_db(meta_config)
            logger.info("保存指标信息到 Meta MySQL")

            # 第五步：为指标名称、描述和别名建立向量索引。
            await self._save_metrics_to_qdrant(metric_infos)
            logger.info("为指标信息建立向量索引")
