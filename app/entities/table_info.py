"""
表元数据业务实体。

用于在 Service 和 Repository 之间传递表的业务信息。
它不是数据库表，也不包含任何 SQLAlchemy 代码。
"""

from dataclasses import dataclass


@dataclass
class TableInfo:
    """系统内部统一使用的表元数据表达。"""

    # 表的唯一标识。
    #
    # 原项目直接使用真实表名作为 id，例如：
    # dim_region
    # fact_order
    id: str

    # DW MySQL 中的真实表名。
    name: str

    # 表的业务角色。
    #
    # fact：事实表，例如订单表。
    # dim：维度表，例如地区表、商品表。
    role: str

    # 表的业务说明。
    #
    # 该内容来自 meta_config.yaml，
    # 例如“订单事实表，记录订单数量和金额等核心指标”。
    description: str
