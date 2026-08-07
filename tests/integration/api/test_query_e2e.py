"""从 HTTP 请求一直验证到真实 DW 查询结果的付费端到端测试。"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_llm,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_LLM_TESTS") != "1",
        reason="set RUN_LIVE_LLM_TESTS=1 to allow a paid DeepSeek request",
    ),
]


def parse_sse_events(response_text: str) -> list[dict]:
    """把 QueryService 返回的 SSE data 行解析成普通事件字典。"""

    return [
        json.loads(line.removeprefix("data: "))
        for line in response_text.splitlines()
        if line.startswith("data: ")
    ]


def test_query_api_returns_verified_east_china_gmv() -> None:
    """真实 DeepSeek、检索系统、Graph 和 DW 应共同返回华东销售总额。"""

    # TestClient 会进入正式 FastAPI lifespan，因此这里使用的不是 Mock：
    # Qdrant、Embedding、Elasticsearch、两个 MySQL 和 DeepSeek 都会真实参与。
    with TestClient(app) as client:
        response = client.post(
            "/api/query",
            json={"query": "查询华东地区的销售总额"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-request-id"]

    events = parse_sse_events(response.text)
    assert not [event for event in events if event["type"] == "error"]

    result_events = [event for event in events if event["type"] == "result"]
    assert result_events == [
        {
            "type": "result",
            "data": [{"销售总额": 107373.0}],
        }
    ]
