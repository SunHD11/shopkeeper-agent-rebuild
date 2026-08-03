"""
字段元数据业务实体。

字段配置中的业务语义、DW 中的真实字段类型，以及抽样得到的示例值，
都会汇总到 ColumnInfo，然后继续写入 Meta MySQL 和 Qdrant。
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ColumnInfo:
    """系统内部统一使用的字段元数据表达。"""

    # 字段唯一标识。
    #
    # 使用“表名.字段名”的形式，避免不同表出现同名字段。
    # 例如：
    # fact_order.order_amount
    # dim_customer.customer_id
    id: str

    # DW 中的真实字段名称，例如 order_amount。
    name: str

    # DW 中的真实字段类型。
    #
    # 不是从 YAML 获取，而是通过 SHOW COLUMNS 从 DW MySQL 查询。
    # 例如：
    # decimal(10,2)
    # varchar(128)
    # int
    type: str

    # 字段的业务角色。
    #
    # primary_key：主键
    # foreign_key：外键
    # measure：度量
    # dimension：维度
    role: str

    # 从 DW MySQL 抽取的少量真实示例值。
    #
    # 使用 Any 是因为字段值可能是字符串、数字、日期等类型。
    # 例如：
    # ["华东", "华南"]
    # [100.5, 268.0]
    examples: list[Any]

    # 字段的业务描述，来自 meta_config.yaml。
    description: str

    # 字段别名，来自 meta_config.yaml。
    #
    # 例如 order_amount 的别名：
    # ["销售额", "订单金额", "收入"]
    alias: list[str]

    # 该字段所属表的 id。
    #
    # 例如：
    # fact_order
    table_id: str
