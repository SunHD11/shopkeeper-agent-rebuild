"""测试原项目风格的元数据业务配置结构。"""

from omegaconf import OmegaConf

from app.conf.app_config import PROJECT_ROOT
from app.conf.meta_config import (
    ColumnConfig,
    MetaConfig,
    MetricConfig,
    TableConfig,
)


def test_metadata_config_dataclasses_describe_business_metadata() -> None:
    """四个 dataclass 能表达字段、表、指标和总配置之间的关系。"""

    column = ColumnConfig(
        name="order_amount",
        role="measure",
        description="订单金额。",
        alias=["销售额", "收入"],
        sync=False,
    )
    table = TableConfig(
        name="fact_order",
        role="fact",
        description="订单事实表。",
        columns=[column],
    )
    metric = MetricConfig(
        name="GMV",
        description="所有订单的成交金额总和。",
        relevant_columns=["fact_order.order_amount"],
        alias=["成交总额"],
    )
    config = MetaConfig(tables=[table], metrics=[metric])

    assert config.tables == [table]
    assert config.tables[0].columns == [column]
    assert config.metrics == [metric]


def test_tables_and_metrics_can_be_built_separately() -> None:
    """总配置的两个部分可为空，以支持原项目的分阶段构建流程。"""

    config = MetaConfig()

    assert config.tables is None
    assert config.metrics is None


def test_yaml_can_be_converted_with_the_original_project_flow() -> None:
    """按原项目 build() 中的方式将 YAML 转为 MetaConfig 对象。"""

    context = OmegaConf.load(PROJECT_ROOT / "conf" / "meta_config.yaml")
    schema = OmegaConf.structured(MetaConfig)
    config = OmegaConf.to_object(OmegaConf.merge(schema, context))

    assert isinstance(config, MetaConfig)
    assert config.tables is not None
    assert config.metrics is not None
    assert len(config.tables) == 5
    assert sum(len(table.columns) for table in config.tables) == 24
    assert len(config.metrics) == 2
    assert isinstance(config.tables[0], TableConfig)
    assert isinstance(config.tables[0].columns[0], ColumnConfig)
    assert isinstance(config.metrics[0], MetricConfig)
