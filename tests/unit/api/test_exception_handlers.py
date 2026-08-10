"""测试流开始前的统一 JSON 错误响应。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.exception_handlers import register_exception_handlers
from app.core.errors import AppError, ErrorCode


def create_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure():
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            "请稍后重试",
            retryable=True,
            status_code=429,
        )

    return TestClient(app)


def test_app_error_handler_returns_stable_public_payload() -> None:
    response = create_client().get("/failure")

    assert response.status_code == 429
    assert response.json() == {
        "type": "error",
        "code": "TOO_MANY_REQUESTS",
        "message": "请稍后重试",
        "request_id": "system",
        "retryable": True,
    }
