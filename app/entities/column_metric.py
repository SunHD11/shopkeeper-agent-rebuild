"""
字段与指标关联业务实体。

用于表达一个指标依赖哪个字段。
例如 GMV 依赖 fact_order.order_amount。
"""

from dataclasses import dataclass


@dataclass
class ColumnMetric:
    """字段和指标之间的关联关系。"""

    # 被指标依赖的字段 id。
    #
    # 例如：
    # fact_order.order_amount
    column_id: str

    # 指标 id。
    #
    # 例如：
    # GMV
    metric_id: str
