"""
MetricInfo 映射器。

负责在指标业务实体和指标 ORM 模型之间双向转换。
"""

from dataclasses import asdict

from app.entities.metric_info import MetricInfo
from app.models.metric_info import MetricInfoMySQL


class MetricInfoMapper:
    """负责 MetricInfo 与 MetricInfoMySQL 之间的双向转换。"""

    @staticmethod
    def to_entity(metric_info_mysql: MetricInfoMySQL) -> MetricInfo:
        """把指标 ORM 模型转换成业务实体。"""

        return MetricInfo(
            id=metric_info_mysql.id,
            name=metric_info_mysql.name,
            description=metric_info_mysql.description,
            relevant_columns=metric_info_mysql.relevant_columns,
            alias=metric_info_mysql.alias,
        )

    @staticmethod
    def to_model(metric_info: MetricInfo) -> MetricInfoMySQL:
        """把指标业务实体转换成 ORM 模型。"""

        return MetricInfoMySQL(**asdict(metric_info))
