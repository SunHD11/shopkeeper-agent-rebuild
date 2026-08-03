"""Load environment-aware, typed application configuration."""

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "conf" / "app_config.yaml"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


@dataclass
class FileLoggingConfig:
    """File logging settings."""

    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class ConsoleLoggingConfig:
    """Console logging settings."""

    enable: bool
    level: str


@dataclass
class LoggingConfig:
    """Combined logging settings."""

    file: FileLoggingConfig
    console: ConsoleLoggingConfig


@dataclass
class DBConfig:
    """MySQL connection settings."""

    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str = ""


@dataclass
class QdrantConfig:
    """Qdrant connection and rebuild namespace settings."""

    host: str
    port: int
    embedding_size: int
    column_collection_name: str
    metric_collection_name: str


@dataclass
class EmbeddingConfig:
    """Text Embeddings Inference settings."""

    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    """Elasticsearch connection and rebuild index settings."""

    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    """OpenAI-compatible language-model settings."""

    model_name: str
    api_key: str = field(repr=False)
    base_url: str = ""


@dataclass
class AppConfig:
    """Top-level application configuration."""

    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig


def load_app_config(
    config_file: Path = DEFAULT_CONFIG_FILE,
    env_file: Path | None = DEFAULT_ENV_FILE,
) -> AppConfig:
    """Load YAML values, resolve environment variables, and enforce the schema."""

    if env_file is not None:
        load_dotenv(env_file, override=False)

    yaml_config = OmegaConf.load(config_file)
    schema = OmegaConf.structured(AppConfig)
    merged = OmegaConf.merge(schema, yaml_config)
    OmegaConf.resolve(merged)
    loaded = OmegaConf.to_object(merged)

    if not isinstance(loaded, AppConfig):
        raise TypeError("OmegaConf did not produce an AppConfig instance")

    return loaded


app_config = load_app_config()
