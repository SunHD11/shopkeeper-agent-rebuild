"""测试 FastAPI Depends 对 Session、Repository、Client 和 Service 的组装。"""

from unittest.mock import Mock

import app.api.dependencies as dependencies_module
from app.core.errors import AppError, ErrorCode
from app.core.query_limiter import QueryLimiter
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.query_service import QueryService


class FakeSessionContext:
    """模拟 session_factory() 返回的异步上下文管理器。"""

    def __init__(self, session: Mock):
        self.session = session
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> Mock:
        self.entered = True
        return self.session

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        self.exited = True


async def test_session_dependencies_yield_and_close_request_sessions(
    monkeypatch,
) -> None:
    """Meta 与 DW Session 都从 require factory 创建，并在生成器结束后退出。"""

    meta_session = Mock(name="meta_session")
    dw_session = Mock(name="dw_session")
    meta_context = FakeSessionContext(meta_session)
    dw_context = FakeSessionContext(dw_session)

    meta_factory = Mock(return_value=meta_context)
    dw_factory = Mock(return_value=dw_context)
    meta_require = Mock(return_value=meta_factory)
    dw_require = Mock(return_value=dw_factory)

    monkeypatch.setattr(
        dependencies_module.meta_mysql_client_manager,
        "require_session_factory",
        meta_require,
    )
    monkeypatch.setattr(
        dependencies_module.dw_mysql_client_manager,
        "require_session_factory",
        dw_require,
    )

    yielded_meta_sessions = [
        session async for session in dependencies_module.get_meta_session()
    ]
    yielded_dw_sessions = [
        session async for session in dependencies_module.get_dw_session()
    ]

    assert yielded_meta_sessions == [meta_session]
    assert yielded_dw_sessions == [dw_session]
    meta_require.assert_called_once_with()
    dw_require.assert_called_once_with()
    meta_factory.assert_called_once_with()
    dw_factory.assert_called_once_with()
    assert meta_context.entered and meta_context.exited
    assert dw_context.entered and dw_context.exited


async def test_mysql_repository_dependencies_preserve_sessions() -> None:
    """两个 MySQL Repository 分别持有对应请求级 Session。"""

    meta_session = Mock(name="meta_session")
    dw_session = Mock(name="dw_session")

    meta_repository = await dependencies_module.get_meta_mysql_repository(meta_session)
    dw_repository = await dependencies_module.get_dw_mysql_repository(dw_session)

    assert isinstance(meta_repository, MetaMySQLRepository)
    assert isinstance(dw_repository, DWMySQLRepository)
    assert meta_repository.session is meta_session
    assert dw_repository.session is dw_session


async def test_external_repository_dependencies_use_required_clients(
    monkeypatch,
) -> None:
    """Embedding、Qdrant 和 ES 均通过 Manager 的 require_client() 取得。"""

    embedding_client = Mock(name="embedding_client")
    qdrant_client = Mock(name="qdrant_client")
    es_client = Mock(name="es_client")

    embedding_require = Mock(return_value=embedding_client)
    qdrant_require = Mock(return_value=qdrant_client)
    es_require = Mock(return_value=es_client)
    monkeypatch.setattr(
        dependencies_module.embedding_client_manager,
        "require_client",
        embedding_require,
    )
    monkeypatch.setattr(
        dependencies_module.qdrant_client_manager,
        "require_client",
        qdrant_require,
    )
    monkeypatch.setattr(
        dependencies_module.es_client_manager,
        "require_client",
        es_require,
    )

    actual_embedding = await dependencies_module.get_embedding_client()
    column_repository = await dependencies_module.get_column_qdrant_repository()
    metric_repository = await dependencies_module.get_metric_qdrant_repository()
    value_repository = await dependencies_module.get_value_es_repository()

    assert actual_embedding is embedding_client
    assert isinstance(column_repository, ColumnQdrantRepository)
    assert isinstance(metric_repository, MetricQdrantRepository)
    assert isinstance(value_repository, ValueESRepository)
    assert column_repository.client is qdrant_client
    assert metric_repository.client is qdrant_client
    assert value_repository.client is es_client
    embedding_require.assert_called_once_with()
    assert qdrant_require.call_count == 2
    es_require.assert_called_once_with()


async def test_query_service_dependency_preserves_all_objects() -> None:
    """最终 Service 接收到的六个依赖与 Depends 上游创建对象完全一致。"""

    objects = {
        "meta_mysql_repository": Mock(name="meta_mysql_repository"),
        "embedding_client": Mock(name="embedding_client"),
        "dw_mysql_repository": Mock(name="dw_mysql_repository"),
        "column_qdrant_repository": Mock(name="column_qdrant_repository"),
        "metric_qdrant_repository": Mock(name="metric_qdrant_repository"),
        "value_es_repository": Mock(name="value_es_repository"),
    }

    service = await dependencies_module.get_query_service(**objects)

    assert isinstance(service, QueryService)
    for attribute_name, expected_object in objects.items():
        assert getattr(service, attribute_name) is expected_object


async def test_query_limiter_dependency_holds_slot_until_response_finishes(
    monkeypatch,
) -> None:
    """yield 依赖覆盖完整 SSE 生命周期，并在退出时释放槽位。"""

    limiter = QueryLimiter(limit=1)
    monkeypatch.setattr(dependencies_module, "query_limiter", limiter)
    dependency = dependencies_module.get_query_limiter()

    yielded_limiter = await anext(dependency)

    assert yielded_limiter is limiter
    assert limiter.active == 1

    await dependency.aclose()
    assert limiter.active == 0


async def test_query_limiter_dependency_rejects_full_capacity(monkeypatch) -> None:
    limiter = QueryLimiter(limit=1)
    await limiter.try_acquire()
    monkeypatch.setattr(dependencies_module, "query_limiter", limiter)
    dependency = dependencies_module.get_query_limiter()

    try:
        await anext(dependency)
    except AppError as error:
        assert error.code == ErrorCode.TOO_MANY_REQUESTS
        assert error.status_code == 429
    else:
        raise AssertionError("满载时必须拒绝新问数请求")

    assert limiter.active == 1
    await limiter.release()
