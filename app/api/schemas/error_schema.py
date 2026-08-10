"""HTTP JSON 与 SSE 共用的公开错误结构。"""

from typing import Literal

from pydantic import BaseModel

from app.core.errors import ErrorCode


class ErrorSchema(BaseModel):
    """前端可稳定消费且不暴露内部异常详情的错误载荷。"""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    request_id: str
    retryable: bool
