"""FastAPI 在流式响应开始前使用的统一 JSON 异常处理器。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.error_schema import ErrorSchema
from app.core.context import request_id_ctx_var
from app.core.errors import AppError, ErrorCode
from app.core.log import logger


def _error_response(error: AppError, request_id: str) -> JSONResponse:
    payload = ErrorSchema(
        code=error.code,
        message=error.public_message,
        request_id=request_id,
        retryable=error.retryable,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=payload.model_dump(mode="json"),
    )


async def app_error_handler(_request: Request, error: AppError) -> JSONResponse:
    """处理并发满载等尚未开始 SSE 的业务异常。"""

    logger.warning(f"请求被拒绝: code={error.code}")
    return _error_response(error, request_id_ctx_var.get())


async def validation_error_handler(
    _request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    """把 Pydantic 默认细节收敛成稳定的 INVALID_REQUEST。"""

    error = AppError(
        ErrorCode.INVALID_REQUEST,
        "请求参数不合法",
        status_code=422,
    )
    return _error_response(error, request_id_ctx_var.get())


def register_exception_handlers(app: FastAPI) -> None:
    """集中注册自定义异常处理器，避免入口文件堆积协议细节。"""

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
