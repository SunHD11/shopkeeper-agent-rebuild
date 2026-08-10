"""测试健康检查路由的 HTTP 状态语义。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_health_service
from app.api.routers.health_router import health_router
from app.services.health_service import DependencyHealth, HealthReport


class FakeHealthService:
    def __init__(self, report: HealthReport) -> None:
        self.report = report

    async def check_readiness(self) -> HealthReport:
        return self.report


def create_client(report: HealthReport) -> TestClient:
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_health_service] = lambda: FakeHealthService(report)
    return TestClient(app)


def test_liveness_does_not_need_external_dependencies() -> None:
    client = create_client(HealthReport(status="unavailable", checks={}))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_returns_200_when_all_checks_are_up() -> None:
    client = create_client(
        HealthReport(
            status="ok",
            checks={"meta_mysql": DependencyHealth(status="up", latency_ms=1.2)},
        )
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_503_when_any_dependency_is_down() -> None:
    client = create_client(
        HealthReport(
            status="unavailable",
            checks={
                "qdrant": DependencyHealth(
                    status="down",
                    latency_ms=5.0,
                    detail="TimeoutError",
                )
            },
        )
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {
            "qdrant": {
                "status": "down",
                "latency_ms": 5.0,
                "detail": "TimeoutError",
            }
        },
    }
