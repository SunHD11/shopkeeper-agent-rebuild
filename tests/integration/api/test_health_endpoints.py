"""使用 rebuild 自管 Docker 服务验证正式健康检查。"""

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = pytest.mark.integration


def test_live_and_ready_endpoints_with_real_services() -> None:
    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "ok"
    assert ready_response.status_code == 200
    report = ready_response.json()
    assert report["status"] == "ok"
    assert all(check["status"] == "up" for check in report["checks"].values())
