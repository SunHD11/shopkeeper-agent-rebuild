"""
指标元数据业务实体。

用于表达一个业务指标的名称、描述、别名，
以及它依赖的底层字段。
"""

from dataclasses import dataclass


@dataclass
class MetricInfo:
    """系统内部统一使用的指标元数据表达。"""

    # 指标唯一标识。
    #
    # 原项目直接使用指标名作为 id，例如：
    # GMV
    # AOV
    id: str

    # 指标名称。
    name: str

    # 指标的业务说明。
    description: str

    # 指标依赖的底层字段列表。
    #
    # 例如 GMV 依赖：
    # ["fact_order.order_amount"]
    relevant_columns: list[str]

    # 指标的其他叫法。
    #
    # 例如 GMV：
    # ["成交总额", "订单总额"]
    alias: list[str]
