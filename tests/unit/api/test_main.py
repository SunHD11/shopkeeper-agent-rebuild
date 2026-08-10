"""测试 FastAPI 根应用装配和 request ID 中间件。"""

import uuid
from unittest.mock import Mock

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

import main as main_module
from app.core.context import request_id_ctx_var


def test_main_app_metadata_and_routes_are_registered() -> None:
    """正式入口包含问数以及存活、就绪检查路径。"""

    assert main_module.app.title == "Shopkeeper Agent Rebuild"
    assert main_module.app.version == "0.1.0"

    operation = main_module.app.openapi()["paths"]["/api/query"]["post"]
    assert operation["summary"] == "执行自然语言问数查询"
    assert operation["tags"] == ["query"]
    assert "/health/live" in main_module.app.openapi()["paths"]
    assert "/health/ready" in main_module.app.openapi()["paths"]


def test_main_app_uses_explicit_frontend_cors_allowlist() -> None:
    """浏览器前端可以访问 API，但不会使用带凭据的通配符 Origin。"""

    cors_middleware = next(
        middleware
        for middleware in main_module.app.user_middleware
        if middleware.cls is CORSMiddleware
    )

    assert cors_middleware.kwargs["allow_origins"] == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert "*" not in cors_middleware.kwargs["allow_origins"]
    assert cors_middleware.kwargs["allow_credentials"] is True


async def test_request_id_middleware_sets_header_and_restores_context(
    monkeypatch,
) -> None:
    """处理请求时日志可读 request ID，响应后 ContextVar 恢复原值。"""

    fixed_request_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr(main_module.uuid, "uuid4", Mock(return_value=fixed_request_id))

    observed_request_ids: list[str] = []

    async def call_next(_request) -> Response:
        observed_request_ids.append(request_id_ctx_var.get())
        return Response(content="ok")

    outer_token = request_id_ctx_var.set("outer-request")
    try:
        response = await main_module.add_request_id(Mock(), call_next)

        assert observed_request_ids == [str(fixed_request_id)]
        assert response.headers["X-Request-ID"] == str(fixed_request_id)
        assert request_id_ctx_var.get() == "outer-request"
    finally:
        request_id_ctx_var.reset(outer_token)


async def test_request_id_context_is_restored_when_handler_fails(
    monkeypatch,
) -> None:
    """下游抛出异常时 finally 仍恢复 ContextVar，异常本身继续传播。"""

    fixed_request_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    monkeypatch.setattr(main_module.uuid, "uuid4", Mock(return_value=fixed_request_id))

    async def failing_call_next(_request):
        assert request_id_ctx_var.get() == str(fixed_request_id)
        raise RuntimeError("handler failed")

    outer_token = request_id_ctx_var.set("outer-request")
    try:
        try:
            await main_module.add_request_id(Mock(), failing_call_next)
        except RuntimeError as error:
            assert str(error) == "handler failed"
        else:
            raise AssertionError("下游异常应继续向上抛出")

        assert request_id_ctx_var.get() == "outer-request"
    finally:
        request_id_ctx_var.reset(outer_token)
