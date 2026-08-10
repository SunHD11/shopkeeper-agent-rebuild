"""测试内部异常到公开错误语义的转换。"""

from app.core.errors import AppError, ErrorCode, classify_exception
from app.core.sql_security import UnsafeSQLError


class FakeProviderError(Exception):
    """模拟带 HTTP 状态码的 OpenAI 兼容 Provider 异常。"""

    def __init__(self, status_code: int, message: str = "provider failed") -> None:
        super().__init__(message)
        self.status_code = status_code


def test_classify_exception_preserves_app_error() -> None:
    original = AppError(
        ErrorCode.INVALID_REQUEST,
        "无效请求",
        status_code=422,
    )

    assert classify_exception(original) is original


def test_classify_exception_maps_sql_and_timeout_without_leaking_details() -> None:
    sql_error = classify_exception(UnsafeSQLError("DROP TABLE secret_table"))
    timeout_error = classify_exception(TimeoutError("10.0.0.8 timed out"))

    assert sql_error.code == ErrorCode.SQL_REJECTED
    assert "secret_table" not in sql_error.public_message
    assert timeout_error.code == ErrorCode.QUERY_TIMEOUT
    assert timeout_error.retryable is True
    assert "10.0.0.8" not in timeout_error.public_message


def test_classify_exception_maps_provider_status_codes() -> None:
    assert classify_exception(FakeProviderError(401)).code == ErrorCode.LLM_AUTH_FAILED
    assert (
        classify_exception(FakeProviderError(402)).code
        == ErrorCode.LLM_BALANCE_INSUFFICIENT
    )
    rate_limited = classify_exception(FakeProviderError(429))
    unavailable = classify_exception(FakeProviderError(503))

    assert rate_limited.code == ErrorCode.LLM_RATE_LIMITED
    assert rate_limited.retryable is True
    assert unavailable.code == ErrorCode.LLM_UNAVAILABLE
    assert unavailable.retryable is True


def test_unknown_exception_becomes_safe_internal_error() -> None:
    error = classify_exception(RuntimeError("mysql://user:password@private-host"))

    assert error.code == ErrorCode.INTERNAL_ERROR
    assert "password" not in error.public_message
