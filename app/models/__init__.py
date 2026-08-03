"""Metadata ORM models."""

# 在包初始化时导入四个模型。
#
# 这样只要执行 import app.models，
# SQLAlchemy 就能把四张表注册到 Base.metadata。
from app.models.column_info import ColumnInfoMySQL
from app.models.column_metric import ColumnMetricMySQL
from app.models.metric_info import MetricInfoMySQL
from app.models.table_info import TableInfoMySQL

# __all__ 用来声明这个包希望公开哪些对象。
#
# 它不是 SQLAlchemy 必需的，但可以让包的公共接口更清晰。
__all__ = [
    "ColumnInfoMySQL",
    "ColumnMetricMySQL",
    "MetricInfoMySQL",
    "TableInfoMySQL",
]
