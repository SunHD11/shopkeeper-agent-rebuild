"""
FastAPI 依赖注入与对象组装。

这个模块把应用级 Client、请求级 MySQL Session、Repository 和 QueryService
按层次连接起来。Router 只声明自己需要 QueryService，不直接理解数据库连接、
Qdrant Collection、Elasticsearch Index 或 Embedding Client 的创建细节。

生命周期层次：

    FastAPI lifespan
        -> 初始化应用级 Client / Engine
    Depends session generator
        -> 为每个请求创建并关闭 MySQL Session
    Repository dependency
        -> 用 Session 或 Client 创建 Repository
    QueryService dependency
        -> 汇总全部业务依赖
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.core.errors import AppError, ErrorCode
from app.core.query_limiter import QueryLimiter
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.health_service import HealthService
from app.services.query_service import QueryService

# 单进程共享同一个计数器，限制的是正在运行的完整 LangGraph 数量。
query_limiter = QueryLimiter(app_config.runtime.max_concurrent_queries)


async def get_meta_session() -> AsyncIterator[AsyncSession]:
    """为一次 HTTP 请求创建并自动关闭 Meta MySQL Session。"""

    # require_session_factory() 会检查 lifespan 是否已经执行 init()。
    # 如果应用生命周期未正确启动，会抛出含义明确的 RuntimeError。
    session_factory = meta_mysql_client_manager.require_session_factory()

    # FastAPI 会执行到 yield，把 Session 注入下游依赖；请求结束后继续执行
    # async with 的退出流程，确保连接归还连接池。
    async with session_factory() as session:
        yield session


async def get_dw_session() -> AsyncIterator[AsyncSession]:
    """为一次 HTTP 请求创建并自动关闭 DW MySQL Session。"""

    session_factory = dw_mysql_client_manager.require_session_factory()
    async with session_factory() as session:
        yield session


async def get_meta_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetaMySQLRepository:
    """用请求级 Meta Session 创建元数据 Repository。"""

    return MetaMySQLRepository(session)


async def get_dw_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_dw_session)],
) -> DWMySQLRepository:
    """用请求级 DW Session 创建数仓 Repository。"""

    return DWMySQLRepository(session)


async def get_embedding_client() -> HuggingFaceEndpointEmbeddings:
    """取得 lifespan 初始化的应用级 Embedding Client。"""

    return embedding_client_manager.require_client()


async def get_column_qdrant_repository() -> ColumnQdrantRepository:
    """使用共享 Qdrant Client 创建字段向量召回 Repository。"""

    return ColumnQdrantRepository(qdrant_client_manager.require_client())


async def get_metric_qdrant_repository() -> MetricQdrantRepository:
    """使用共享 Qdrant Client 创建指标向量召回 Repository。"""

    return MetricQdrantRepository(qdrant_client_manager.require_client())


async def get_value_es_repository() -> ValueESRepository:
    """使用共享 Elasticsearch Client 创建字段值召回 Repository。"""

    return ValueESRepository(es_client_manager.require_client())


async def get_query_service(
    meta_mysql_repository: Annotated[
        MetaMySQLRepository,
        Depends(get_meta_mysql_repository),
    ],
    embedding_client: Annotated[
        HuggingFaceEndpointEmbeddings,
        Depends(get_embedding_client),
    ],
    dw_mysql_repository: Annotated[
        DWMySQLRepository,
        Depends(get_dw_mysql_repository),
    ],
    column_qdrant_repository: Annotated[
        ColumnQdrantRepository,
        Depends(get_column_qdrant_repository),
    ],
    metric_qdrant_repository: Annotated[
        MetricQdrantRepository,
        Depends(get_metric_qdrant_repository),
    ],
    value_es_repository: Annotated[
        ValueESRepository,
        Depends(get_value_es_repository),
    ],
) -> QueryService:
    """汇总一次问数请求所需依赖并创建 QueryService。"""

    # QueryService 只接收已经准备好的工具，不负责识别它们来自哪种连接池或
    # 客户端管理器，因此 Service 可以在单元测试中轻松替换为 Mock。
    return QueryService(
        meta_mysql_repository=meta_mysql_repository,
        embedding_client=embedding_client,
        dw_mysql_repository=dw_mysql_repository,
        column_qdrant_repository=column_qdrant_repository,
        metric_qdrant_repository=metric_qdrant_repository,
        value_es_repository=value_es_repository,
    )


async def get_health_service() -> HealthService:
    """组装只读的应用级 readiness 探测服务。"""

    return HealthService(
        meta_mysql_manager=meta_mysql_client_manager,
        dw_mysql_manager=dw_mysql_client_manager,
        qdrant_manager=qdrant_client_manager,
        es_manager=es_client_manager,
        embedding_manager=embedding_client_manager,
        timeout_seconds=app_config.runtime.health_timeout_seconds,
    )


async def get_query_limiter() -> AsyncIterator[QueryLimiter]:
    """在创建数据库 Session 前抢占槽位，并在整个流式响应结束后释放。"""

    if not await query_limiter.try_acquire():
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            "当前问数请求较多，请稍后重试",
            retryable=True,
            status_code=429,
        )

    try:
        # FastAPI 的 yield 依赖会覆盖完整响应生命周期。SSE 正常结束、中途异常
        # 或客户端断连后都会进入 finally，不会泄漏并发槽位。
        yield query_limiter
    finally:
        await query_limiter.release()
