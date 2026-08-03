"""Manage the shared asynchronous Qdrant client."""

from qdrant_client import AsyncQdrantClient

from app.conf.app_config import QdrantConfig, app_config


class QdrantClientManager:
    """Create a Qdrant client only when the application lifecycle starts."""

    def __init__(self, config: QdrantConfig):
        self.config = config
        self.client: AsyncQdrantClient | None = None

    def _get_url(self) -> str:
        """Return the configured Qdrant HTTP endpoint."""

        return f"http://{self.config.host}:{self.config.port}"

    def init(self) -> None:
        """Initialize the client once."""

        if self.client is None:
            self.client = AsyncQdrantClient(url=self._get_url())

    def require_client(self) -> AsyncQdrantClient:
        """Return the initialized client or explain the lifecycle mistake."""

        if self.client is None:
            raise RuntimeError("QdrantClientManager.init() must be called first")
        return self.client

    async def close(self) -> None:
        """Close the client safely, even when called more than once."""

        if self.client is not None:
            await self.client.close()
        self.client = None


qdrant_client_manager = QdrantClientManager(app_config.qdrant)
