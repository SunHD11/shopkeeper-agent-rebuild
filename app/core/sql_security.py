"""LLM 生成 SQL 的只读安全边界。"""

import re


class UnsafeSQLError(ValueError):
    """SQL 超出自然语言问数服务允许的只读范围。"""


# 先遮蔽字符串、注释和反引号标识符，再检查真正参与执行的 SQL 关键字。
# 这样 ``SELECT 'delete'`` 不会因为普通文本中出现 delete 而被误判。
_NON_CODE_PATTERN = re.compile(
    r"'(?:\\.|''|[^'])*'"
    r'|"(?:\\.|""|[^"])*"'
    r"|`(?:``|[^`])*`"
    r"|/\*.*?\*/"
    r"|--[ \t].*?$"
    r"|#.*?$",
    flags=re.DOTALL | re.MULTILINE,
)

_WRITE_PATTERN = re.compile(
    r"\b(?:insert|update|delete|drop|alter|truncate|create|replace|merge|"
    r"grant|revoke|call|load|lock|unlock|set|use|handler|do)\b"
    r"|\binto\s+(?:outfile|dumpfile)\b"
    r"|\bfor\s+update\b"
    r"|\block\s+in\s+share\s+mode\b",
    flags=re.IGNORECASE,
)


def validate_read_only_sql(sql: str) -> str:
    """校验并规范化一条只读查询，返回去掉结尾分号的 SQL。"""

    normalized_sql = sql.strip()
    if not normalized_sql:
        raise UnsafeSQLError("SQL 不能为空")

    # 允许模型习惯性输出一个结尾分号，但禁止第二条语句。
    if normalized_sql.endswith(";"):
        normalized_sql = normalized_sql[:-1].rstrip()

    masked_sql = _NON_CODE_PATTERN.sub(" ", normalized_sql)
    if ";" in masked_sql:
        raise UnsafeSQLError("只允许执行一条 SQL 查询")

    first_keyword = re.match(r"^\s*([a-z]+)\b", masked_sql, re.IGNORECASE)
    if first_keyword is None or first_keyword.group(1).lower() not in {
        "select",
        "with",
    }:
        raise UnsafeSQLError("只允许执行 SELECT 或 WITH 查询")

    blocked_keyword = _WRITE_PATTERN.search(masked_sql)
    if blocked_keyword is not None:
        raise UnsafeSQLError(f"SQL 包含禁止的操作: {blocked_keyword.group(0).upper()}")

    return normalized_sql
