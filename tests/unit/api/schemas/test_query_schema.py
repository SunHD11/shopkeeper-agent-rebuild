"""测试自然语言问数请求体的 Pydantic 校验。"""

import pytest
from pydantic import ValidationError

from app.api.schemas.query_schema import QuerySchema


def test_query_schema_strips_surrounding_whitespace() -> None:
    """有效问题去除首尾空格和换行，内部文字保持不变。"""

    schema = QuerySchema(query=" \n 查询华东地区的销售总额 \t")

    assert schema.query == "查询华东地区的销售总额"


@pytest.mark.parametrize(
    "query", ["", " ", "\n\t"], ids=["empty", "space", "whitespace"]
)
def test_query_schema_rejects_empty_or_blank_question(query: str) -> None:
    """空字符串与纯空白字符串都不能进入 QueryService。"""

    with pytest.raises(ValidationError):
        QuerySchema(query=query)


def test_query_schema_rejects_question_over_limit() -> None:
    """超过 2000 字符的问题在 HTTP 边界被拒绝。"""

    with pytest.raises(ValidationError):
        QuerySchema(query="问" * 2001)
