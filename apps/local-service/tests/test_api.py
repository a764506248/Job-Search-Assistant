from fastapi.testclient import TestClient

from job_search_assistant.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_decision_api_accepts_camel_case_contract() -> None:
    response = client.post(
        "/v1/decisions/evaluate",
        json={
            "jobText": "负责 RAG 应用研发",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
        },
    )

    assert response.status_code == 200
    assert response.json()["materialStrategy"] == "custom"
