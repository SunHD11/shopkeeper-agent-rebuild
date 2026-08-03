"""Manage the Text Embeddings Inference client."""

from huggingface_hub import AsyncInferenceClient, InferenceClient
from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientManager:
    """Create and reuse a LangChain-compatible TEI embeddings client."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client: HuggingFaceEndpointEmbeddings | None = None

    def _get_url(self) -> str:
        """Return the configured TEI endpoint."""

        return f"http://{self.config.host}:{self.config.port}"

    def init(self) -> None:
        """Initialize the stateless HTTP client once."""

        if self.client is None:
            # langchain-huggingface 1.2+ only accepts repository IDs in ``model``.
            # Point its underlying HTTP clients at our local TEI server instead.
            client = HuggingFaceEndpointEmbeddings(model=self.config.model)
            client.client = InferenceClient(base_url=self._get_url())
            client.async_client = AsyncInferenceClient(base_url=self._get_url())
            self.client = client

    def require_client(self) -> HuggingFaceEndpointEmbeddings:
        """Return the initialized client or explain the lifecycle mistake."""

        if self.client is None:
            raise RuntimeError("EmbeddingClientManager.init() must be called first")
        return self.client

    async def close(self) -> None:
        """Reset the stateless wrapper for lifecycle symmetry."""

        self.client = None


embedding_client_manager = EmbeddingClientManager(app_config.embedding)
