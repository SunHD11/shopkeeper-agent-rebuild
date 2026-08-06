"""
元数据知识库构建脚本入口。

这个文件是项目的 Composition Root（对象装配入口），负责：

1. 接收命令行传入的 meta_config.yaml 路径；
2. 初始化 MySQL、Qdrant、Elasticsearch 和 Embedding 客户端；
3. 创建两个 MySQL Session 和所有 Repository；
4. 将依赖注入 MetaKnowledgeService；
5. 启动一次完整的元数据知识库构建；
6. 无论成功还是失败，都安全关闭客户端。

它不包含元数据构建的具体业务规则。表、字段、指标如何组合，
以及按照什么顺序写入各存储系统，都由 MetaKnowledgeService 负责。
"""

# argparse 用于解析命令行中的 -c / --conf 参数。
import argparse

# asyncio.run() 用于从同步 main() 启动异步 build()。
import asyncio

# Path 将命令行字符串转换成明确的文件路径对象。
from pathlib import Path

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.core.context import request_context
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


async def build(config_path: Path) -> None:
    """
    初始化依赖并执行一次完整的元数据知识库构建。

    参数：
        config_path：
            元数据业务配置文件路径，例如 conf/meta_config.yaml。

    这个函数负责基础设施生命周期和对象装配，真正的业务流程通过
    MetaKnowledgeService.build(config_path) 执行。
    """

    # 将初始化也放进 try 中。
    # 如果某个 Manager 初始化失败，finally 仍会尝试清理此前已经创建的资源。
    # rebuild 中各 Manager 的 close() 都支持尚未初始化或重复关闭的情况。
    try:
        # 初始化 Meta MySQL Engine 和 SessionFactory。
        meta_mysql_client_manager.init()

        # 初始化 DW MySQL Engine 和 SessionFactory。
        # Meta 与 DW 使用独立 Manager，避免把查询发到错误数据库。
        dw_mysql_client_manager.init()

        # 初始化共享的异步 Qdrant Client。
        qdrant_client_manager.init()

        # 初始化文本向量化客户端。
        embedding_client_manager.init()

        # 初始化异步 Elasticsearch Client。
        es_client_manager.init()

        # require_session_factory() 同时承担生命周期检查：
        # 如果前面漏掉 init()，这里会给出明确的 RuntimeError。
        meta_session_factory = meta_mysql_client_manager.require_session_factory()
        dw_session_factory = dw_mysql_client_manager.require_session_factory()

        # Qdrant、Embedding 和 Elasticsearch 是进程级共享客户端。
        qdrant_client = qdrant_client_manager.require_client()
        embedding_client = embedding_client_manager.require_client()
        es_client = es_client_manager.require_client()

        # 同时打开 Meta MySQL 与 DW MySQL Session。
        #
        # meta_session：用于保存结构化元数据。
        # dw_session：用于读取真实 DW 字段类型和值。
        #
        # 离开 async with 后，两个 Session 都会自动关闭。
        async with (
            meta_session_factory() as meta_session,
            dw_session_factory() as dw_session,
        ):
            # Meta Repository 只使用 Meta MySQL Session。
            meta_mysql_repository = MetaMySQLRepository(meta_session)

            # DW Repository 只使用 DW MySQL Session。
            dw_mysql_repository = DWMySQLRepository(dw_session)

            # 字段和指标共享 Qdrant Client，但写入不同 Collection。
            column_qdrant_repository = ColumnQdrantRepository(qdrant_client)
            metric_qdrant_repository = MetricQdrantRepository(qdrant_client)

            # Value Repository 使用 Elasticsearch Client，
            # 负责 value_index 的创建、写入和查询。
            value_es_repository = ValueESRepository(es_client)

            # 将所有基础设施依赖统一注入业务 Service。
            meta_knowledge_service = MetaKnowledgeService(
                meta_mysql_repository=meta_mysql_repository,
                dw_mysql_repository=dw_mysql_repository,
                column_qdrant_repository=column_qdrant_repository,
                embedding_client=embedding_client,
                value_es_repository=value_es_repository,
                metric_qdrant_repository=metric_qdrant_repository,
            )

            # 进入真正的业务构建流程：
            # YAML + DW -> Entities -> Meta MySQL / Qdrant / Elasticsearch。
            await meta_knowledge_service.build(config_path)

    finally:
        # 无论构建成功还是中途抛出异常，客户端都必须关闭。
        #
        # Session 已由 async with 关闭；这里关闭的是 ClientManager 持有的
        # 共享 Client 或 MySQL Engine。
        await embedding_client_manager.close()
        await es_client_manager.close()
        await qdrant_client_manager.close()
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()


def main() -> None:
    """解析命令行配置路径，并启动异步元数据知识库构建。"""

    # 创建命令行参数解析器。
    parser = argparse.ArgumentParser(
        description="Build the metadata knowledge base.",
    )

    # required=True 表示调用脚本时必须明确提供配置路径。
    #
    # 以下两种调用方式等价：
    # -c conf/meta_config.yaml
    # --conf conf/meta_config.yaml
    parser.add_argument(
        "-c",
        "--conf",
        required=True,
        help="Path to the metadata YAML configuration file.",
    )

    args = parser.parse_args()

    # 为这次构建设置稳定的日志 request_id。
    # MetaKnowledgeService 中的所有日志都会带上同一个上下文标识。
    with request_context("meta-knowledge-build"):
        # argparse 返回字符串；Service.build() 的契约使用 Path。
        asyncio.run(build(Path(args.conf)))


if __name__ == "__main__":
    main()
