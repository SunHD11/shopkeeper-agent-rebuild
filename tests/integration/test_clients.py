"""Integration tests against the configured Docker services."""

import pytest
from sqlalchemy import text

from app.clients.embedding_client_manager import EmbeddingClientManager
from app.clients.es_client_manager import ESClientManager
from app.clients.mysql_client_manager import MySQLClientManager
from app.clients.qdrant_client_manager import QdrantClientManager
from app.conf.app_config import app_config

pytestmark = pytest.mark.integration


async def test_mysql_meta_and_read_only_dw_connections() -> None:
    meta = MySQLClientManager(app_config.db_meta)
    dw = MySQLClientManager(app_config.db_dw)
    meta.init()
    dw.init()
    try:
        async with meta.require_session_factory()() as session:
            table_count = await session.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = 'meta'"
                )
            )
            assert table_count == 4

        async with dw.require_session_factory()() as session:
            order_count = await session.scalar(text("SELECT COUNT(*) FROM fact_order"))
            assert order_count == 115
            grants = (
                await session.execute(text("SHOW GRANTS FOR CURRENT_USER"))
            ).scalars()
            rendered_grants = "\n".join(grants)
            assert "SELECT ON `dw`.*" in rendered_grants
            assert "ALL PRIVILEGES ON `dw`.*" not in rendered_grants
    finally:
        await meta.close()
        await dw.close()


async def test_qdrant_connection() -> None:
    manager = QdrantClientManager(app_config.qdrant)
    manager.init()
    try:
        result = await manager.require_client().get_collections()
        assert isinstance(result.collections, list)
    finally:
        await manager.close()


async def test_elasticsearch_connection() -> None:
    manager = ESClientManager(app_config.es)
    manager.init()
    try:
        health = await manager.require_client().cluster.health()
        assert health["status"] in {"green", "yellow"}
    finally:
        await manager.close()


async def test_embedding_connection_and_dimension() -> None:
    manager = EmbeddingClientManager(app_config.embedding)
    manager.init()
    try:
        client = manager.require_client()
        vectors = await client.aembed_documents(["销售额", "华北地区", "会员等级"])
        assert len(vectors) == 3
        assert all(
            len(vector) == app_config.qdrant.embedding_size for vector in vectors
        )
        assert vectors[0] != vectors[1]
    finally:
        await manager.close()
