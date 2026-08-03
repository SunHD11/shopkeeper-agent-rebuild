"""Manage the shared asynchronous Elasticsearch client."""

from elasticsearch import AsyncElasticsearch

from app.conf.app_config import ESConfig, app_config


class ESClientManager:
    """Create an Elasticsearch client only when the lifecycle starts."""

    def __init__(self, config: ESConfig):
        self.config = config
        self.client: AsyncElasticsearch | None = None

    def _get_url(self) -> str:
        """Return the configured Elasticsearch endpoint."""

        return f"http://{self.config.host}:{self.config.port}"

    def init(self) -> None:
        """Initialize the client once."""

        if self.client is None:
            self.client = AsyncElasticsearch(hosts=[self._get_url()])

    def require_client(self) -> AsyncElasticsearch:
        """Return the initialized client or explain the lifecycle mistake."""

        if self.client is None:
            raise RuntimeError("ESClientManager.init() must be called first")
        return self.client

    async def close(self) -> None:
        """Close the client safely, even when called more than once."""

        if self.client is not None:
            await self.client.close()
        self.client = None


es_client_manager = ESClientManager(app_config.es)
