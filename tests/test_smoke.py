from fastapi.testclient import TestClient

from fake_llm import FakeLLM
from main import app


def test_fake_llm_interface_untouched():
    llm = FakeLLM(["hello"])
    assert llm.complete("hi") == "hello"
    assert llm.call_count == 1


def test_health_and_observability_do_not_need_api_key():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    report = client.get("/observability/report")
    assert report.status_code == 200
    body = report.json()
    assert "calls" in body
    assert "total_cost" in body
    assert "avg_latency" in body
    assert "alerts" in body
