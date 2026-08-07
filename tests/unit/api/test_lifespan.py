"""测试 FastAPI lifespan 对所有应用级 ClientManager 的初始化和释放。"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

import app.api.lifespan as lifespan_module


def patch_manager_lifecycle(monkeypatch):
    """把五个 Manager 的 init/close 替换为可断言 Mock。"""

    managers = [
        lifespan_module.qdrant_client_manager,
        lifespan_module.embedding_client_manager,
        lifespan_module.es_client_manager,
        lifespan_module.meta_mysql_client_manager,
        lifespan_module.dw_mysql_client_manager,
    ]
    lifecycle_mocks = []

    for manager in managers:
        init_mock = Mock()
        close_mock = AsyncMock()
        monkeypatch.setattr(manager, "init", init_mock)
        monkeypatch.setattr(manager, "close", close_mock)
        lifecycle_mocks.append((init_mock, close_mock))

    return lifecycle_mocks


async def test_lifespan_initializes_before_yield_and_closes_after(
    monkeypatch,
) -> None:
    """进入 lifespan 后全部初始化，退出后全部异步关闭。"""

    lifecycle_mocks = patch_manager_lifecycle(monkeypatch)

    async with lifespan_module.lifespan(FastAPI()):
        for init_mock, close_mock in lifecycle_mocks:
            init_mock.assert_called_once_with()
            close_mock.assert_not_awaited()

    for _, close_mock in lifecycle_mocks:
        close_mock.assert_awaited_once_with()


async def test_lifespan_closes_resources_when_initialization_fails(
    monkeypatch,
) -> None:
    """某个 init 抛错时 finally 仍尝试关闭所有可能已创建的资源。"""

    lifecycle_mocks = patch_manager_lifecycle(monkeypatch)
    es_init_mock = lifecycle_mocks[2][0]
    es_init_mock.side_effect = RuntimeError("es init failed")

    with pytest.raises(RuntimeError, match="es init failed"):
        async with lifespan_module.lifespan(FastAPI()):
            pytest.fail("初始化失败后不应进入应用运行阶段")

    # Qdrant 和 Embedding 在 ES 之前已经初始化；Meta/DW 初始化尚未执行。
    lifecycle_mocks[0][0].assert_called_once_with()
    lifecycle_mocks[1][0].assert_called_once_with()
    es_init_mock.assert_called_once_with()
    lifecycle_mocks[3][0].assert_not_called()
    lifecycle_mocks[4][0].assert_not_called()

    # close() 都具有幂等性，因此 finally 可以安全地统一尝试关闭。
    for _, close_mock in lifecycle_mocks:
        close_mock.assert_awaited_once_with()
