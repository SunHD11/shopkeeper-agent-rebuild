"""
自然语言问数查询服务。

QueryService 位于 FastAPI 路由层和 LangGraph Agent 之间，负责把一次 HTTP
查询请求转换成一次完整的 Agent 工作流执行：

    用户自然语言问题
        -> 创建初始 DataAgentState
        -> 组装 DataAgentContext
        -> 调用 graph.astream()
        -> 消费节点 progress / result 事件
        -> 包装为 SSE 文本
        -> 交给 FastAPI StreamingResponse

Service 不创建数据库连接，也不直接实现召回、SQL 生成或 SQL 执行。所有外部
依赖都由 FastAPI Depends 创建后注入，具体业务步骤仍由 Graph 中的节点负责。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.conf.app_config import RuntimeConfig, app_config
from app.core.context import request_id_ctx_var
from app.core.errors import AppError, ErrorCode, classify_exception
from app.core.log import logger
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def format_sse_event(event: Any) -> str:
    """把一个 Agent 事件编码成 Server-Sent Events 文本。

    SSE 的每条消息必须满足：

    - 内容以 ``data: `` 开头；
    - 消息结尾包含两个换行符；
    - data 后面的 JSON 保留中文；
    - Decimal、date 等 JSON 默认不支持的值可以安全转换成字符串。

    例如输入：

        {"type": "progress", "step": "生成SQL", "status": "running"}

    输出：

        data: {"type": "progress", ...}\n\n
    """

    event_json = json.dumps(
        event,
        ensure_ascii=False,
        default=str,
    )
    return f"data: {event_json}\n\n"


class QueryService:
    """封装一次在线问数请求所需的 Graph 调用与流式响应编排。"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        value_es_repository: ValueESRepository,
        runtime_config: RuntimeConfig | None = None,
    ) -> None:
        """保存由 API 依赖层注入的一次请求所需外部工具。

        QueryService 不负责连接或关闭这些资源：

        - MySQL Session 由 FastAPI yield 依赖管理请求级生命周期；
        - Qdrant、Embedding 和 ES Client 由应用 lifespan 管理；
        - Repository 只封装具体存储访问能力。
        """

        # Meta MySQL 用于在线合并节点补齐字段、表和主外键元数据。
        self.meta_mysql_repository = meta_mysql_repository

        # DW MySQL 用于获取数据库环境、EXPLAIN 校验和执行最终 SQL。
        self.dw_mysql_repository = dw_mysql_repository

        # Embedding 与两个 Qdrant Repository 负责字段、指标向量召回。
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository

        # Elasticsearch Repository 负责用户问题中真实字段值的全文召回。
        self.value_es_repository = value_es_repository

        # 总超时是整条在线问数的统一最后边界，包含模型、召回、SQL 校验与执行。
        self.runtime_config = runtime_config or app_config.runtime

    async def query(
        self,
        query: str,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        """执行一次完整问数 Graph，并逐条产出 SSE 文本。

        这是一个异步生成器。调用方法不会一次性等待整个 Agent 执行完毕，而是
        每收到一个节点通过 ``runtime.stream_writer`` 写出的事件，就立即 yield
        一条 SSE 消息，前端因此可以实时显示执行进度。

        流式响应一旦开始发送，HTTP 状态码通常已经确定。如果 Graph 中途失败，
        Service 无法再把响应改成传统的 500 JSON，因此会把错误统一包装成最后
        一条 ``type=error`` 的 SSE 事件。
        """

        current_request_id = request_id or request_id_ctx_var.get()

        try:
            # API Schema 将来会负责请求体校验，但 Service 仍保留一层业务保护，
            # 避免测试、脚本或其他调用方绕过 FastAPI 后传入纯空白问题。
            normalized_query = query.strip()
            if not normalized_query:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "用户问题不能为空",
                    status_code=422,
                )

            # State 只保存会在节点之间流转、合并和覆盖的动态业务数据。
            # 初始阶段只需要 query，其余 keywords、召回结果、SQL 等字段由节点
            # 按 Graph 顺序逐步写入。
            state = DataAgentState(query=normalized_query)

            # Context 保存本次 Graph 执行期间保持不变的外部工具。节点通过
            # runtime.context["依赖名"] 取得它们，而不是把客户端塞进 State。
            context = DataAgentContext(
                column_qdrant_repository=self.column_qdrant_repository,
                embedding_client=self.embedding_client,
                metric_qdrant_repository=self.metric_qdrant_repository,
                value_es_repository=self.value_es_repository,
                meta_mysql_repository=self.meta_mysql_repository,
                dw_mysql_repository=self.dw_mysql_repository,
            )

            # stream_mode="custom" 表示只消费节点通过 stream_writer(...) 主动
            # 写出的事件，例如：
            #
            # - progress：节点 running / success / error；
            # - result：run_sql 返回的最终查询结果。
            #
            # Graph 内部 State 的每次变化不会直接暴露给 API 调用方。
            # asyncio.timeout 对整条异步迭代生效。即使某个第三方调用自身没有
            # 设置超时，也不能无限占用一个并发槽位和两条 MySQL Session。
            async with asyncio.timeout(self.runtime_config.query_timeout_seconds):
                async for event in graph.astream(
                    input=state,
                    context=context,
                    stream_mode="custom",
                ):
                    yield format_sse_event(event)

        except asyncio.CancelledError:
            # 浏览器关闭页面或断开 SSE 时，Starlette 会取消生成器。取消必须继续
            # 向上传播，才能终止 Graph 并让依赖层及时关闭数据库 Session。
            logger.info("客户端断开连接，取消当前问数任务")
            raise

        except Exception as error:
            # 原异常仅写入服务端日志；发送给前端的是稳定、无连接信息和堆栈的
            # 公开文案。request_id 让运维仍能准确关联这次失败。
            classified_error = classify_exception(error)
            logger.exception(
                f"问数失败: code={classified_error.code}, "
                f"error_type={type(error).__name__}"
            )
            error_event = {
                "type": "error",
                "code": classified_error.code,
                "message": classified_error.public_message,
                "request_id": current_request_id,
                "retryable": classified_error.retryable,
            }
            yield format_sse_event(error_event)
