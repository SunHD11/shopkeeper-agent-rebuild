"""Unit tests for explicit and secret-safe client lifecycles."""

import pytest

from app.clients.embedding_client_manager import EmbeddingClientManager
from app.clients.es_client_manager import ESClientManager
from app.clients.mysql_client_manager import MySQLClientManager
from app.clients.qdrant_client_manager import QdrantClientManager
from app.conf.app_config import app_config


def test_mysql_url_masks_password() -> None:
    manager = MySQLClientManager(app_config.db_dw)
    assert app_config.db_dw.password not in str(manager._get_url())


@pytest.mark.parametrize(
    "manager",
    [
        MySQLClientManager(app_config.db_dw),
        QdrantClientManager(app_config.qdrant),
        ESClientManager(app_config.es),
        EmbeddingClientManager(app_config.embedding),
    ],
)
def test_client_access_requires_initialization(manager: object) -> None:
    accessor_name = (
        "require_session_factory"
        if isinstance(manager, MySQLClientManager)
        else "require_client"
    )
    with pytest.raises(RuntimeError):
        getattr(manager, accessor_name)()


async def test_close_operations_are_idempotent() -> None:
    managers = [
        MySQLClientManager(app_config.db_dw),
        QdrantClientManager(app_config.qdrant),
        ESClientManager(app_config.es),
        EmbeddingClientManager(app_config.embedding),
    ]
    for manager in managers:
        await manager.close()
        await manager.close()
