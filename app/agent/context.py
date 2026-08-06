"""
电商问数 Agent 的运行时上下文定义。

Context 用于保存一次 LangGraph 执行过程中，各个节点共同使用的外部依赖，
包括 Embedding 客户端、Qdrant Repository、Elasticsearch Repository，
以及分别面向元数据库和原始数据仓库的 MySQL Repository。

这些对象属于“完成任务所需的工具”，不会随着节点执行不断产生和变化，
因此应当放在 Context 中，而不是放进会被 LangGraph 合并和记录的 State 中。

节点可以通过 ``runtime.context["依赖名称"]`` 取得对应的工具。
"""

from typing import TypedDict

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class DataAgentContext(TypedDict):
    """一次 LangGraph 问数任务中所有节点可以共同使用的运行时依赖。"""

    # 字段向量仓储。
    #
    # 主要使用节点：recall_column。
    #
    # 字段召回节点先用 embedding_client 把“销售额”“地区”等关键词转换成
    # 查询向量，再调用这个 Repository 从字段 Qdrant Collection 中检索语义
    # 相近的字段，最终获得 list[ColumnInfo]，而不是 Qdrant 原始 Point。
    column_qdrant_repository: ColumnQdrantRepository

    # Embedding 客户端。
    #
    # 主要使用节点：recall_column、recall_metric。
    #
    # Qdrant 保存的是字段和指标的向量，因此在线查询词也必须经过相同模型
    # 转换成相同维度的向量，然后才能执行相似度检索。例如：
    #
    #     embedding = await embedding_client.aembed_query("销售总额")
    #
    # 当前项目通过 HuggingFaceEndpointEmbeddings 访问已经部署好的 Embedding 服务。
    embedding_client: HuggingFaceEndpointEmbeddings

    # 指标向量仓储。
    #
    # 主要使用节点：recall_metric。
    #
    # 它接收查询向量，从指标 Qdrant Collection 中召回 GMV、AOV 等业务指标，
    # 并把底层检索结果转换成 MetricInfo 业务实体。
    metric_qdrant_repository: MetricQdrantRepository

    # 字段真实取值的 Elasticsearch 仓储。
    #
    # 主要使用节点：recall_value。
    #
    # 用户问题中的“华东”“黄金会员”“手机”等内容更像字段真实值，
    # 适合通过全文检索定位。例如检索“华东”后，可以获得：
    #
    #     ValueInfo(
    #         value="华东",
    #         column_id="dim_region.region_name",
    #     )
    #
    # 后续合并节点据此知道“华东”应当用于哪个字段的 WHERE 条件。
    value_es_repository: ValueESRepository

    # 元数据 MySQL 仓储。
    #
    # 主要使用节点：merge_retrieved_info。
    #
    # Qdrant 和 Elasticsearch 的职责是尽可能召回相关候选，但它们不保证
    # 返回生成 SQL 所需的完整关系结构。合并节点会使用这个 Repository：
    #
    # 1. 按字段 id 补齐指标依赖但没有被向量召回的字段；
    # 2. 根据字段的 table_id 获取完整表信息；
    # 3. 补齐多表 JOIN 所需的主键和外键字段；
    # 4. 把三路召回结果整理成 TableInfoState 和 MetricInfoState。
    meta_mysql_repository: MetaMySQLRepository

    # 原始数据仓库 MySQL 仓储。
    #
    # 主要使用节点：add_extra_context、validate_sql、run_sql。
    #
    # 它在在线问数链路中承担三个不同任务：
    #
    # 1. add_extra_context 调用 get_db_info()，获取数据库方言和版本；
    # 2. validate_sql 调用 validate()，通过真实数据库检查候选 SQL；
    # 3. run_sql 调用 run()，执行最终 SQL 并取得查询结果。
    #
    # 节点只表达“查询、校验或执行”的业务意图，连接和 SQLAlchemy 细节仍然
    # 封装在 Repository 中。
    dw_mysql_repository: DWMySQLRepository
