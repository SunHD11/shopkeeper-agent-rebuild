"""
FastAPI 应用级资源生命周期管理。

外部 Client 和 SQLAlchemy Engine 应在应用启动时初始化一次，并被所有请求复用；
如果每个请求都重新创建，会产生额外连接开销并难以正确释放资源。MySQL Session
仍由 dependencies.py 为每个请求单独创建，避免请求之间共享事务状态。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化应用级外部资源，并在应用关闭时可靠释放。"""

    # 当前不需要读取 app，但保留 FastAPI 规定的 lifespan 函数签名。
    _ = app

    try:
        # init() 具有幂等性：已经初始化的 Manager 不会重复创建 Client/Engine。
        # 初始化本身通常不立即发起真实查询，连接会在第一次使用时按需建立。
        qdrant_client_manager.init()
        embedding_client_manager.init()
        es_client_manager.init()
        meta_mysql_client_manager.init()
        dw_mysql_client_manager.init()

        # yield 之前是应用启动阶段，yield 期间 FastAPI 正常处理 HTTP 请求。
        yield

    finally:
        # 无论应用正常关闭还是启动/运行中出现异常，都尝试释放已经创建的资源。
        # 使用与依赖方向相反的大致顺序关闭，避免连接池和网络 Client 悬挂。
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()
        await es_client_manager.close()
        await embedding_client_manager.close()
        await qdrant_client_manager.close()
