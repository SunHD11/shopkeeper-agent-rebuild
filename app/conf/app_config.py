"""
应用主配置

定义 conf/app_config.yaml 在程序中的结构化配置对象
项目启动后会在这里一次性完成配置文件加载和类型化转换，其他模块只需要导入 app_config
就可以按属性方式读取日志 MySQL Qdrant Embedding Elasticsearch 和 LLM 配置
"""

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf

# 通过当前 Python 文件的位置定位项目根目录，而不是依赖终端当前目录。
#
# 当前文件：
#     shopkeeper-agent-rebuild/app/conf/app_config.py
#
# parents[2]：
#     shopkeeper-agent-rebuild
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 默认配置文件和环境变量文件都从项目根目录定位。
# 这样 API、脚本和测试从其他工作目录启动时，仍然能读取到正确文件。
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "conf" / "app_config.yaml"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


@dataclass
class File:
    """文件日志配置"""

    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    """控制台日志配置"""

    enable: bool
    level: str


@dataclass
class LoggingConfig:
    """日志总配置"""

    file: File
    console: Console


@dataclass
class DBConfig:
    """MySQL 连接配置"""

    host: str
    port: int
    user: str

    # repr=False 防止打印 AppConfig 时把数据库密码一起输出到终端或日志。
    password: str = field(repr=False)

    # 保留默认空值，既兼容原项目完整填写 database 的方式，也允许某些只连接
    # MySQL Server、暂时不选择具体数据库的工具复用这个配置结构。
    database: str = ""


@dataclass
class QdrantConfig:
    """Qdrant 连接、向量维度和 rebuild 独立 Collection 配置。"""

    host: str
    port: int
    embedding_size: int

    # 原项目只运行一套 Qdrant Collection，所以没有把名称放入配置结构。
    # rebuild 与原项目可能共用同一个 Qdrant 服务，为避免读写到原项目数据，
    # 必须通过配置指定属于 rebuild 的字段和指标 Collection 名称。
    column_collection_name: str
    metric_collection_name: str


@dataclass
class EmbeddingConfig:
    """Embedding 服务配置"""

    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    """Elasticsearch 配置"""

    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    """大模型调用配置"""

    model_name: str

    # API Key 与数据库密码一样属于敏感信息，禁止进入 dataclass 的 repr。
    api_key: str = field(repr=False)

    # 默认空字符串兼容使用模型 Provider 默认地址的场景；当前 YAML 会明确配置
    # 硅基流动的 OpenAI 兼容 API 地址。
    base_url: str = ""

    # 单次模型请求的网络超时和自动重试次数。只重试模型网络层的临时失败，
    # 不重试已经进入 DW MySQL 的 SQL，避免一次问数被重复执行。
    timeout_seconds: float = 60
    max_retries: int = 1


@dataclass
class RuntimeConfig:
    """在线问数执行边界。"""

    query_timeout_seconds: float = 120
    retrieval_timeout_seconds: float = 20
    health_timeout_seconds: float = 5
    max_concurrent_queries: int = 4


@dataclass
class APIConfig:
    """HTTP 边界配置。"""

    cors_allowed_origins: list[str]


@dataclass
class AppConfig:
    """项目级总配置入口"""

    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig
    runtime: RuntimeConfig
    api: APIConfig


def load_app_config(
    config_file: Path = DEFAULT_CONFIG_FILE,
    env_file: Path | None = DEFAULT_ENV_FILE,
) -> AppConfig:
    """加载 YAML 和环境变量，并转换成经过类型约束的 AppConfig。"""

    # 默认先读取项目根目录的 .env，让 YAML 中的 ${oc.env:变量名} 可以解析。
    # override=False 表示不覆盖操作系统或启动命令已经显式设置的环境变量。
    # 测试缺失环境变量时可以传入 env_file=None，避免自动加载项目 .env。
    if env_file is not None:
        load_dotenv(env_file, override=False)

    # 读取 YAML 中的实际配置值。
    yaml_config = OmegaConf.load(config_file)

    # 根据 AppConfig 和各级 dataclass 建立结构化 Schema。
    # Schema 会拒绝 YAML 中拼写错误或代码中不存在的配置字段。
    schema = OmegaConf.structured(AppConfig)

    # 把实际配置合并进 Schema。
    # 例如 YAML 中如果存在 qdrant.column_collection_name，QdrantConfig 中也必须
    # 声明同名字段，否则 OmegaConf 会立即抛出 ConfigKeyError。
    merged = OmegaConf.merge(schema, yaml_config)

    # 主动解析 ${oc.env:...}，让缺失密码或 API Key 的问题在启动阶段尽早暴露，
    # 而不是等到第一次访问数据库或大模型时才出现难以定位的认证错误。
    OmegaConf.resolve(merged)

    # 将 DictConfig 转换成真正的 AppConfig、DBConfig 等 dataclass 对象，
    # 后续代码即可使用 app_config.db_dw.port 这样的属性访问方式。
    loaded = OmegaConf.to_object(merged)

    # 正常情况下 OmegaConf 会返回 AppConfig。保留显式检查可以防止未来 Schema
    # 被意外改成普通字典后，错误悄悄传播到各个客户端管理器。
    if not isinstance(loaded, AppConfig):
        raise TypeError("OmegaConf did not produce an AppConfig instance")

    return loaded


# 模块导入时加载默认配置，供项目其他模块统一使用。
app_config = load_app_config()

if __name__ == "__main__":
    # 简单测试：只打印非敏感字段，验证配置文件能够正常加载。
    print(app_config.es.host)
