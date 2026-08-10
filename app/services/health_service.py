"""检查在线问数所依赖的本地基础服务是否真正可用。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text

from app.clients.embedding_client_manager import EmbeddingClientManager
from app.clients.es_client_manager import ESClientManager
from app.clients.mysql_client_manager import MySQLClientManager
from app.clients.qdrant_client_manager import QdrantClientManager


@dataclass(frozen=True)
class DependencyHealth:
    """Service 层的一项依赖探测结果，不依赖 HTTP/Pydantic。"""

    status: Literal["up", "down"]
    latency_ms: float
    detail: str | None = None


@dataclass(frozen=True)
class HealthReport:
    """Service 层的就绪状态，由 Router 转换为公开响应 Schema。"""

    status: Literal["ok", "unavailable"]
    checks: dict[str, DependencyHealth]


class HealthService:
    """并行探测 Meta/DW MySQL、Qdrant、ES 和本地 Embedding。"""

    def __init__(
        self,
        *,
        meta_mysql_manager: MySQLClientManager,
        dw_mysql_manager: MySQLClientManager,
        qdrant_manager: QdrantClientManager,
        es_manager: ESClientManager,
        embedding_manager: EmbeddingClientManager,
        timeout_seconds: float,
    ) -> None:
        self.meta_mysql_manager = meta_mysql_manager
        self.dw_mysql_manager = dw_mysql_manager
        self.qdrant_manager = qdrant_manager
        self.es_manager = es_manager
        self.embedding_manager = embedding_manager
        self.timeout_seconds = timeout_seconds

    async def _check_mysql(self, manager: MySQLClientManager) -> None:
        """真实借出一个连接并执行最小查询，验证连接和账号都可用。"""

        async with manager.require_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def _check_qdrant(self) -> None:
        """读取 Collection 列表，验证 Qdrant HTTP API。"""

        await self.qdrant_manager.require_client().get_collections()

    async def _check_es(self) -> None:
        """调用 Elasticsearch ping；False 也必须视为不可用。"""

        if not await self.es_manager.require_client().ping():
            raise RuntimeError("Elasticsearch ping returned false")

    async def _check_embedding(self) -> None:
        """执行一个最小本地向量请求，验证模型已完成加载。"""

        embedding = await self.embedding_manager.require_client().aembed_query("health")
        if not embedding:
            raise RuntimeError("Embedding service returned an empty vector")

    async def _probe(
        self,
        operation: Callable[[], Awaitable[None]],
    ) -> DependencyHealth:
        """为单项探测附加独立超时并把内部异常收敛为状态。"""

        started_at = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await operation()
        except Exception as error:
            latency_ms = (time.perf_counter() - started_at) * 1000
            return DependencyHealth(
                status="down",
                latency_ms=round(latency_ms, 2),
                # readiness 是运维接口，只暴露异常类型，不回传含地址、账号的原文。
                detail=type(error).__name__,
            )

        latency_ms = (time.perf_counter() - started_at) * 1000
        return DependencyHealth(
            status="up",
            latency_ms=round(latency_ms, 2),
        )

    async def check_readiness(self) -> HealthReport:
        """并行检查全部必要依赖；不调用会收费的 DeepSeek。"""

        names = (
            "meta_mysql",
            "dw_mysql",
            "qdrant",
            "elasticsearch",
            "embedding",
        )
        results = await asyncio.gather(
            self._probe(lambda: self._check_mysql(self.meta_mysql_manager)),
            self._probe(lambda: self._check_mysql(self.dw_mysql_manager)),
            self._probe(self._check_qdrant),
            self._probe(self._check_es),
            self._probe(self._check_embedding),
        )
        checks = dict(zip(names, results, strict=True))
        ready = all(item.status == "up" for item in checks.values())
        return HealthReport(
            status="ok" if ready else "unavailable",
            checks=checks,
        )
