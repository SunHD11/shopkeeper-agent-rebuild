"""测试元数据知识库构建入口的依赖装配和资源生命周期。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pytest import MonkeyPatch

from app.core.context import request_id_ctx_var
from app.scripts import build_meta_knowledge


class AsyncSessionContext:
    """模拟 async with 使用的异步 Session 上下文管理器。"""

    def __init__(self, session: object):
        self.session = session
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> object:
        self.entered = True
        return self.session

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> bool:
        self.exited = True
        return False


def create_manager() -> Mock:
    """创建带同步 init() 和异步 close() 的 ClientManager Mock。"""

    manager = Mock()
    manager.init = Mock()
    manager.close = AsyncMock()
    return manager


def configure_dependencies(monkeypatch: MonkeyPatch) -> SimpleNamespace:
    """替换入口模块的外部依赖，并返回后续断言需要的 Mock。"""

    meta_manager = create_manager()
    dw_manager = create_manager()
    qdrant_manager = create_manager()
    embedding_manager = create_manager()
    es_manager = create_manager()

    meta_session = object()
    dw_session = object()
    meta_context = AsyncSessionContext(meta_session)
    dw_context = AsyncSessionContext(dw_session)
    meta_factory = Mock(return_value=meta_context)
    dw_factory = Mock(return_value=dw_context)
    meta_manager.require_session_factory.return_value = meta_factory
    dw_manager.require_session_factory.return_value = dw_factory

    qdrant_client = object()
    embedding_client = object()
    es_client = object()
    qdrant_manager.require_client.return_value = qdrant_client
    embedding_manager.require_client.return_value = embedding_client
    es_manager.require_client.return_value = es_client

    meta_repository = object()
    dw_repository = object()
    column_repository = object()
    metric_repository = object()
    value_repository = object()
    meta_repository_class = Mock(return_value=meta_repository)
    dw_repository_class = Mock(return_value=dw_repository)
    column_repository_class = Mock(return_value=column_repository)
    metric_repository_class = Mock(return_value=metric_repository)
    value_repository_class = Mock(return_value=value_repository)

    service = Mock()
    service.build = AsyncMock()
    service_class = Mock(return_value=service)

    monkeypatch.setattr(
        build_meta_knowledge,
        "meta_mysql_client_manager",
        meta_manager,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "dw_mysql_client_manager",
        dw_manager,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "qdrant_client_manager",
        qdrant_manager,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "embedding_client_manager",
        embedding_manager,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "es_client_manager",
        es_manager,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "MetaMySQLRepository",
        meta_repository_class,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "DWMySQLRepository",
        dw_repository_class,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "ColumnQdrantRepository",
        column_repository_class,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "MetricQdrantRepository",
        metric_repository_class,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "ValueESRepository",
        value_repository_class,
    )
    monkeypatch.setattr(
        build_meta_knowledge,
        "MetaKnowledgeService",
        service_class,
    )

    return SimpleNamespace(
        managers=[
            meta_manager,
            dw_manager,
            qdrant_manager,
            embedding_manager,
            es_manager,
        ],
        meta_manager=meta_manager,
        dw_manager=dw_manager,
        qdrant_manager=qdrant_manager,
        embedding_manager=embedding_manager,
        es_manager=es_manager,
        meta_context=meta_context,
        dw_context=dw_context,
        meta_factory=meta_factory,
        dw_factory=dw_factory,
        meta_session=meta_session,
        dw_session=dw_session,
        qdrant_client=qdrant_client,
        embedding_client=embedding_client,
        es_client=es_client,
        meta_repository=meta_repository,
        dw_repository=dw_repository,
        column_repository=column_repository,
        metric_repository=metric_repository,
        value_repository=value_repository,
        meta_repository_class=meta_repository_class,
        dw_repository_class=dw_repository_class,
        column_repository_class=column_repository_class,
        metric_repository_class=metric_repository_class,
        value_repository_class=value_repository_class,
        service=service,
        service_class=service_class,
    )


async def test_build_initializes_dependencies_and_runs_service(
    monkeypatch: MonkeyPatch,
) -> None:
    """入口会使用正确客户端创建 Repository，并把它们注入 Service。"""

    dependencies = configure_dependencies(monkeypatch)
    config_path = Path("conf/meta_config.yaml")

    await build_meta_knowledge.build(config_path)

    for manager in dependencies.managers:
        manager.init.assert_called_once_with()
        manager.close.assert_awaited_once_with()

    dependencies.meta_manager.require_session_factory.assert_called_once_with()
    dependencies.dw_manager.require_session_factory.assert_called_once_with()
    dependencies.qdrant_manager.require_client.assert_called_once_with()
    dependencies.embedding_manager.require_client.assert_called_once_with()
    dependencies.es_manager.require_client.assert_called_once_with()
    dependencies.meta_factory.assert_called_once_with()
    dependencies.dw_factory.assert_called_once_with()
    assert dependencies.meta_context.entered is True
    assert dependencies.meta_context.exited is True
    assert dependencies.dw_context.entered is True
    assert dependencies.dw_context.exited is True

    dependencies.meta_repository_class.assert_called_once_with(
        dependencies.meta_session
    )
    dependencies.dw_repository_class.assert_called_once_with(dependencies.dw_session)
    dependencies.column_repository_class.assert_called_once_with(
        dependencies.qdrant_client
    )
    dependencies.metric_repository_class.assert_called_once_with(
        dependencies.qdrant_client
    )
    dependencies.value_repository_class.assert_called_once_with(dependencies.es_client)
    dependencies.service_class.assert_called_once_with(
        meta_mysql_repository=dependencies.meta_repository,
        dw_mysql_repository=dependencies.dw_repository,
        column_qdrant_repository=dependencies.column_repository,
        embedding_client=dependencies.embedding_client,
        value_es_repository=dependencies.value_repository,
        metric_qdrant_repository=dependencies.metric_repository,
    )
    dependencies.service.build.assert_awaited_once_with(config_path)


async def test_build_closes_all_clients_when_service_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    """业务构建抛出异常时，Session 和全部 ClientManager 仍会清理。"""

    dependencies = configure_dependencies(monkeypatch)
    dependencies.service.build.side_effect = RuntimeError("build failed")

    with pytest.raises(RuntimeError, match="build failed"):
        await build_meta_knowledge.build(Path("conf/meta_config.yaml"))

    assert dependencies.meta_context.exited is True
    assert dependencies.dw_context.exited is True
    for manager in dependencies.managers:
        manager.close.assert_awaited_once_with()


async def test_build_closes_managers_when_initialization_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    """某个 Manager 初始化失败时，也会清理已创建和未创建的 Manager。"""

    dependencies = configure_dependencies(monkeypatch)
    dependencies.qdrant_manager.init.side_effect = RuntimeError("qdrant init failed")

    with pytest.raises(RuntimeError, match="qdrant init failed"):
        await build_meta_knowledge.build(Path("conf/meta_config.yaml"))

    dependencies.meta_manager.init.assert_called_once_with()
    dependencies.dw_manager.init.assert_called_once_with()
    dependencies.qdrant_manager.init.assert_called_once_with()
    dependencies.embedding_manager.init.assert_not_called()
    dependencies.es_manager.init.assert_not_called()
    for manager in dependencies.managers:
        manager.close.assert_awaited_once_with()
    dependencies.service.build.assert_not_awaited()


def test_main_parses_config_path_and_runs_build(
    monkeypatch: MonkeyPatch,
) -> None:
    """CLI 的 -c 参数会转换成 Path，并交给异步 build()。"""

    build = AsyncMock()
    monkeypatch.setattr(build_meta_knowledge, "build", build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_meta_knowledge.py",
            "-c",
            "conf/meta_config.yaml",
        ],
    )

    build_meta_knowledge.main()

    build.assert_awaited_once_with(Path("conf/meta_config.yaml"))
    assert request_id_ctx_var.get() == "system"
