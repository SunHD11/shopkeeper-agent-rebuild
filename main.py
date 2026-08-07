"""
Shopkeeper Agent rebuild 的 FastAPI 应用入口。

这个模块负责创建应用、注册生命周期、挂载业务 Router，并为每个 HTTP 请求建立
独立 request ID。具体问数逻辑位于 QueryService 和 LangGraph 节点中，入口文件
不直接创建 Repository 或执行 SQL。

开发环境可通过以下命令启动：

    uv run fastapi dev main.py
"""

import uuid

from fastapi import FastAPI, Request, Response

from app.api.lifespan import lifespan
from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var

# lifespan 统一管理 Qdrant、Embedding、Elasticsearch 和两个 MySQL Engine。
# title、description 和 version 会显示在 /docs 与 /openapi.json 中。
app = FastAPI(
    title="Shopkeeper Agent Rebuild",
    description="基于 LangGraph 与元数据知识库的自然语言问数服务。",
    version="0.1.0",
    lifespan=lifespan,
)

# 如果没有 include_router，即使 Router 函数已经编写，FastAPI 也不会注册路径。
app.include_router(query_router)


@app.middleware("http")
async def add_request_id(
    request: Request,
    call_next,
) -> Response:
    """为一次 HTTP 请求建立日志关联 ID，并在响应结束后恢复上下文。"""

    # 每次请求创建新的 UUID 字符串。它会被 app.core.log 的 Loguru patch 自动
    # 注入日志，方便把同一次流式问数产生的所有节点日志关联起来。
    request_id = str(uuid.uuid4())
    token = request_id_ctx_var.set(request_id)

    try:
        response = await call_next(request)

        # 把相同 ID 返回给调用方。前端报告问题时可以附带该值，后端即可在日志中
        # 精确定位这一整条 Agent 执行链路。
        response.headers["X-Request-ID"] = request_id
        return response

    finally:
        # ContextVar 是请求上下文局部变量，但仍应使用 token 恢复旧值，避免测试、
        # 后台任务或同一执行上下文中的后续代码继承错误 request ID。
        request_id_ctx_var.reset(token)
