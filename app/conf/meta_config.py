"""
元数据知识构建配置。

这个文件只负责定义 meta_config.yaml 在 Python 中对应的数据结构，
暂时不负责读取 YAML，也不负责把元数据写入数据库。

原项目会在后续的 MetaKnowledgeService.build() 中使用 OmegaConf：
1. 读取 meta_config.yaml；
2. 根据这里的 MetaConfig 创建结构化 schema；
3. 将 YAML 转换成下面这些 dataclass 对象；
4. 再启动 Meta MySQL、Qdrant 和 Elasticsearch 的构建流程。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ColumnConfig:
    """
    单个字段的业务配置。

    name：DW 数据仓库中的真实字段名。
    role：字段的业务角色，例如主键、外键、维度或度量。
    description：字段的业务含义。
    alias：用户可能使用的其他叫法。
    sync：是否把该字段的真实取值同步到 Elasticsearch。
    """

    name: str
    role: str
    description: str
    alias: list[str]
    sync: bool


@dataclass
class TableConfig:
    """
    单张 DW 表的业务配置。

    name：DW 数据仓库中的真实表名。
    role：表的业务角色，目前主要是事实表 fact 或维度表 dim。
    description：整张表的业务含义。
    columns：需要纳入元数据知识库的字段配置列表。
    """

    name: str
    role: str
    description: str
    columns: list[ColumnConfig]


@dataclass
class MetricConfig:
    """
    单个业务指标的配置。

    name：指标名称，例如 GMV。
    description：指标的业务解释。
    relevant_columns：计算或理解该指标所依赖的字段。
    alias：用户可能使用的指标别名。
    """

    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]


@dataclass
class MetaConfig:
    """
    元数据知识构建的总配置。

    tables 和 metrics 都允许为空，这与原项目保持一致：
    后续可以只构建表字段知识，也可以只构建指标知识。
    """

    tables: Optional[list[TableConfig]] = None
    metrics: Optional[list[MetricConfig]] = None
