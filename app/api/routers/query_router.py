"""
自然语言问数 HTTP 路由。

Router 只负责 HTTP 边界工作：解析并校验请求体、通过 Depends 获取 QueryService，
再把 Service 的异步 SSE 生成器交给 StreamingResponse。它不直接创建 Repository、
调用 Agent 节点或执行 SQL，从而保持 API 层轻薄。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_limiter, get_query_service
from app.api.schemas.query_schema import QuerySchema
from app.core.context import request_id_ctx_var
from app.core.query_limiter import QueryLimiter
from app.services.query_service import QueryService

# 使用统一 /api 前缀，后续增加 health、metadata 等 Router 时仍能保持清晰结构。
query_router = APIRouter(
    prefix="/api",
    tags=["query"],
)


@query_router.post(
    "/query",
    summary="执行自然语言问数查询",
    response_class=StreamingResponse,
)
async def query_handler(
    request_body: QuerySchema,
    # 把槽位依赖放在 QueryService 之前，让满载请求在创建两个 MySQL Session 和
    # 六个 Repository 前就返回 429。
    limiter: Annotated[QueryLimiter, Depends(get_query_limiter)],
    query_service: Annotated[QueryService, Depends(get_query_service)],
) -> StreamingResponse:
    """接收自然语言问题，并以 Server-Sent Events 持续返回执行过程。"""

    # QuerySchema 已完成去除首尾空白、非空和长度校验。
    # QueryService.query() 返回异步生成器，StreamingResponse 会边迭代边发送，
    # 不会等待整个 LangGraph 和 SQL 查询结束后才一次性返回。
    # limiter 的实际占用和释放由 yield 依赖管理；保留局部引用能明确表示该依赖
    # 是本路由的执行门槛，而不是一个未使用的装饰性参数。
    _ = limiter
    request_id = request_id_ctx_var.get()

    return StreamingResponse(
        content=query_service.query(
            request_body.query,
            request_id=request_id,
        ),
        media_type="text/event-stream",
        headers={
            # SSE 不应被浏览器或中间代理缓存，否则实时进度可能被延迟或复用。
            "Cache-Control": "no-cache",
            # Nginx 识别此响应头后会关闭代理缓冲，允许事件及时到达客户端。
            "X-Accel-Buffering": "no",
        },
    )
