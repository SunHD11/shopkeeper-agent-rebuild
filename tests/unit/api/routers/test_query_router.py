"""测试 ``POST /api/query`` 的请求校验、依赖注入与 SSE 响应。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_query_service
from app.api.routers.query_router import query_router


class FakeQueryService:
    """提供可记录查询参数的本地 SSE 异步生成器。"""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def query(self, query: str):
        self.queries.append(query)
        yield 'data: {"type":"progress","status":"running"}\n\n'
        yield 'data: {"type":"result","data":[{"GMV":125000.5}]}\n\n'


def create_test_client() -> tuple[TestClient, FakeQueryService, FastAPI]:
    """创建不含真实 lifespan、且覆盖 QueryService 依赖的测试应用。"""

    test_app = FastAPI()
    test_app.include_router(query_router)
    service = FakeQueryService()

    # Router 仍执行真实 Depends 解析，但最底层 QueryService 被本地替身覆盖，
    # 因此不会创建数据库 Session 或访问任何外部服务。
    test_app.dependency_overrides[get_query_service] = lambda: service
    return TestClient(test_app), service, test_app


def test_query_router_streams_service_events_and_headers() -> None:
    """有效请求返回 text/event-stream，并保留 Service 事件顺序。"""

    client, service, _ = create_test_client()

    response = client.post(
        "/api/query",
        json={"query": "  查询华东地区的销售总额  "},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert service.queries == ["查询华东地区的销售总额"]
    assert response.text == (
        'data: {"type":"progress","status":"running"}\n\n'
        'data: {"type":"result","data":[{"GMV":125000.5}]}\n\n'
    )


def test_query_router_rejects_blank_question_before_service_stream() -> None:
    """纯空白问题由 QuerySchema 返回 422，不启动 QueryService 生成器。"""

    client, service, _ = create_test_client()

    response = client.post(
        "/api/query",
        json={"query": "   \n"},
    )

    assert response.status_code == 422
    assert service.queries == []


def test_query_router_requires_query_field() -> None:
    """缺少 query 字段时 FastAPI 自动返回请求体校验错误。"""

    client, service, _ = create_test_client()

    response = client.post("/api/query", json={})

    assert response.status_code == 422
    assert service.queries == []
