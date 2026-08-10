"""测试 readiness 对五项本地基础服务的并行探测。"""

import asyncio
from unittest.mock import AsyncMock, Mock

from app.services.health_service import HealthService


class FakeConnectionContext:
    def __init__(self, connection: Mock) -> None:
        self.connection = connection

    async def __aenter__(self) -> Mock:
        return self.connection

    async def __aexit__(self, *_args) -> None:
        return None


def create_health_service(*, timeout_seconds: float = 1) -> tuple[HealthService, dict]:
    """构造不会连接真实 Docker 服务的 Manager 替身。"""

    meta_connection = Mock(execute=AsyncMock())
    dw_connection = Mock(execute=AsyncMock())
    meta_engine = Mock(
        connect=Mock(return_value=FakeConnectionContext(meta_connection))
    )
    dw_engine = Mock(connect=Mock(return_value=FakeConnectionContext(dw_connection)))
    meta_manager = Mock(require_engine=Mock(return_value=meta_engine))
    dw_manager = Mock(require_engine=Mock(return_value=dw_engine))

    qdrant_client = Mock(get_collections=AsyncMock(return_value=[]))
    qdrant_manager = Mock(require_client=Mock(return_value=qdrant_client))
    es_client = Mock(ping=AsyncMock(return_value=True))
    es_manager = Mock(require_client=Mock(return_value=es_client))
    embedding_client = Mock(aembed_query=AsyncMock(return_value=[0.1, 0.2]))
    embedding_manager = Mock(require_client=Mock(return_value=embedding_client))

    service = HealthService(
        meta_mysql_manager=meta_manager,
        dw_mysql_manager=dw_manager,
        qdrant_manager=qdrant_manager,
        es_manager=es_manager,
        embedding_manager=embedding_manager,
        timeout_seconds=timeout_seconds,
    )
    return service, {
        "meta_connection": meta_connection,
        "dw_connection": dw_connection,
        "qdrant_client": qdrant_client,
        "es_client": es_client,
        "embedding_client": embedding_client,
    }


async def test_readiness_reports_all_dependencies_up() -> None:
    service, objects = create_health_service()

    report = await service.check_readiness()

    assert report.status == "ok"
    assert set(report.checks) == {
        "meta_mysql",
        "dw_mysql",
        "qdrant",
        "elasticsearch",
        "embedding",
    }
    assert all(check.status == "up" for check in report.checks.values())
    objects["meta_connection"].execute.assert_awaited_once()
    objects["dw_connection"].execute.assert_awaited_once()
    objects["qdrant_client"].get_collections.assert_awaited_once_with()
    objects["es_client"].ping.assert_awaited_once_with()
    objects["embedding_client"].aembed_query.assert_awaited_once_with("health")


async def test_readiness_reports_down_without_exposing_raw_error() -> None:
    service, objects = create_health_service()
    objects["es_client"].ping.return_value = False

    report = await service.check_readiness()

    assert report.status == "unavailable"
    assert report.checks["elasticsearch"].status == "down"
    assert report.checks["elasticsearch"].detail == "RuntimeError"
    assert report.checks["meta_mysql"].status == "up"


async def test_each_readiness_probe_has_an_independent_timeout() -> None:
    service, _ = create_health_service(timeout_seconds=0.001)

    async def slow_embedding() -> None:
        await asyncio.sleep(1)

    service._check_embedding = slow_embedding
    report = await service.check_readiness()

    assert report.status == "unavailable"
    assert report.checks["embedding"].status == "down"
    assert report.checks["embedding"].detail == "TimeoutError"
