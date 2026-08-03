"""Verify every Python client against the configured local services."""

import asyncio

from sqlalchemy import text

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.core.context import request_context
from app.core.log import logger


async def check_clients() -> None:
    """Connect, exercise, and close all configured clients."""

    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    embedding_client_manager.init()

    try:
        meta_factory = meta_mysql_client_manager.require_session_factory()
        async with meta_factory() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = 'meta'"
                )
            )
            logger.info("[OK] Meta MySQL: {} tables", result.scalar_one())

        dw_factory = dw_mysql_client_manager.require_session_factory()
        async with dw_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM fact_order"))
            logger.info("[OK] DW MySQL: {} orders", result.scalar_one())

        qdrant = qdrant_client_manager.require_client()
        collections = await qdrant.get_collections()
        logger.info("[OK] Qdrant: {} collections", len(collections.collections))

        es = es_client_manager.require_client()
        health = await es.cluster.health()
        logger.info("[OK] Elasticsearch: {}", health["status"])

        embedding = embedding_client_manager.require_client()
        vector = await embedding.aembed_query("销售额")
        if len(vector) != 1024:
            raise RuntimeError(f"Expected 1024 dimensions, got {len(vector)}")
        logger.info("[OK] Embedding: {} dimensions", len(vector))
    finally:
        await embedding_client_manager.close()
        await es_client_manager.close()
        await qdrant_client_manager.close()
        await dw_mysql_client_manager.close()
        await meta_mysql_client_manager.close()


def main() -> None:
    """Run diagnostics with a stable request ID in every log line."""

    with request_context("client-check"):
        asyncio.run(check_clients())


if __name__ == "__main__":
    main()
