"""
字段取值业务实体。

用于把 DW 中的真实字段值同步到 Elasticsearch，
帮助系统判断用户问题中的业务值属于哪个字段。
"""

from dataclasses import dataclass


@dataclass
class ValueInfo:
    """字段具体取值及其所属字段的业务表达。"""

    # 字段值文档的唯一标识。
    #
    # 原项目使用“字段id.字段值”的形式，例如：
    # dim_region.region_name.华东
    id: str

    # 字段的真实取值，例如：
    # 华东
    # 广东
    # 黄金会员
    value: str

    # 该值所属字段的 id，例如：
    # dim_region.region_name
    column_id: str
