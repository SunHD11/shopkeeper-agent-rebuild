"""跨 API、Service 和基础设施边界使用的统一错误语义。"""

from enum import StrEnum

from app.core.sql_security import UnsafeSQLError


class ErrorCode(StrEnum):
    """前端可以稳定判断、不会随异常文案变化的错误码。"""

    INVALID_REQUEST = "INVALID_REQUEST"
    TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_BALANCE_INSUFFICIENT = "LLM_BALANCE_INSUFFICIENT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
    SQL_REJECTED = "SQL_REJECTED"
    SQL_VALIDATION_FAILED = "SQL_VALIDATION_FAILED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """带公开文案和 HTTP 语义的应用异常。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable
        self.status_code = status_code


def classify_exception(error: Exception) -> AppError:
    """把第三方异常转换成不会泄漏内部连接信息的稳定错误。"""

    if isinstance(error, AppError):
        return error

    if isinstance(error, UnsafeSQLError):
        return AppError(
            ErrorCode.SQL_REJECTED,
            "生成的 SQL 未通过只读安全检查",
            status_code=400,
        )

    if isinstance(error, TimeoutError):
        return AppError(
            ErrorCode.QUERY_TIMEOUT,
            "查询处理超时，请缩小查询范围后重试",
            retryable=True,
            status_code=504,
        )

    class_name = type(error).__name__
    status_code = getattr(error, "status_code", None)
    lower_message = str(error).lower()

    if class_name in {
        "AuthenticationError",
        "PermissionDeniedError",
    } or status_code in {
        401,
        403,
    }:
        return AppError(
            ErrorCode.LLM_AUTH_FAILED,
            "大模型服务认证失败，请检查服务端密钥配置",
            status_code=502,
        )

    if status_code == 402 or any(
        word in lower_message for word in ("balance", "insufficient funds", "余额")
    ):
        return AppError(
            ErrorCode.LLM_BALANCE_INSUFFICIENT,
            "大模型账户余额不足，请联系服务管理员",
            status_code=502,
        )

    if class_name == "RateLimitError" or status_code == 429:
        return AppError(
            ErrorCode.LLM_RATE_LIMITED,
            "大模型服务请求过于频繁，请稍后重试",
            retryable=True,
            status_code=503,
        )

    if class_name in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
    } or (isinstance(status_code, int) and status_code >= 500):
        return AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "大模型服务暂时不可用，请稍后重试",
            retryable=True,
            status_code=503,
        )

    if isinstance(error, ValueError) and "SQL" in str(error).upper():
        return AppError(
            ErrorCode.SQL_VALIDATION_FAILED,
            "生成的 SQL 未通过数据库校验",
            status_code=422,
        )

    return AppError(
        ErrorCode.INTERNAL_ERROR,
        "查询处理失败，请携带 request_id 联系服务管理员",
        status_code=500,
    )
