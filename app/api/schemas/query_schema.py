"""
自然语言问数接口的请求体定义。

Schema 位于 HTTP 边界，负责在请求进入 QueryService 前完成基础结构和文本校验。
FastAPI 会根据 Pydantic 模型自动解析 JSON、返回 422 校验错误并生成 OpenAPI 文档。
"""

from pydantic import BaseModel, Field, field_validator


class QuerySchema(BaseModel):
    """``POST /api/query`` 的自然语言问题请求体。"""

    # Field 约束同时会进入 Swagger/OpenAPI 文档：
    # - min_length 阻止空字符串；
    # - max_length 限制异常大的 Prompt 输入；
    # - examples 帮助调用者理解请求格式。
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="需要转换成数据查询的自然语言问题。",
        examples=["查询华东地区最近三个月的销售总额"],
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """去除首尾空白，并拒绝只包含空格或换行的问题。"""

        normalized_query = value.strip()
        if not normalized_query:
            raise ValueError("用户问题不能为空")
        return normalized_query
