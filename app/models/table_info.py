"""
`table_info` ORM 模型

负责定义元数据库中表元数据表的结构，保存纳入知识库的表名、角色和说明
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TableInfoMySQL(Base):
    """MySQL 数据库中表元数据表的 ORM 模型"""

    __tablename__ = "table_info"
    # 定义表结构字段
    # Mapped[str] 表示这个字段不能为空。
    # primary_key=True 表示它是主键。
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="表编号")
    name: Mapped[str | None] = mapped_column(String(128), comment="表名称")
    role: Mapped[str | None] = mapped_column(String(32), comment="表类型(fact/dim)")
    description: Mapped[str | None] = mapped_column(Text, comment="表描述")
