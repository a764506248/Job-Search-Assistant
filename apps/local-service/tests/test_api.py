from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_is_served(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    response = client.get("/")

    assert response.status_code == 200
    assert "本地管理中心" in response.text


def test_decision_api_accepts_camel_case_contract(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
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


def test_capture_job_is_idempotent(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "jobs": [
            {
                "platform": "boss",
                "platformJobId": "job-123",
                "url": "https://www.zhipin.com/job_detail/job-123.html",
                "title": "AI 应用开发工程师",
                "companyName": "示例公司",
                "description": "负责 RAG 应用研发",
                "skills": ["Python", "RAG"],
                "capturedAt": "2026-09-28T08:00:00Z",
                "source": "dom",
            }
        ]
    }

    first = client.post("/v1/jobs/capture", json=payload)
    second = client.post("/v1/jobs/capture", json=payload)

    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "jobIds": ["job-123"]}
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "jobIds": []}

    listing = client.get("/v1/jobs")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    snapshot_id = listing.json()["items"][0]["id"]

    deleted = client.delete(f"/v1/jobs/{snapshot_id}")
    assert deleted.status_code == 204
    assert client.get("/v1/jobs").json()["total"] == 0


def test_jd_analysis_returns_evidence_and_default_strategy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    text = "熟悉Python。985、211院校优先。"

    response = client.post("/v1/jd/analyze", json={"jobText": text})

    assert response.status_code == 200
    result = response.json()
    assert result["hasRiskSignals"] is True
    assert result["riskRequirements"][0]["level"] == "preferred"
    evidence = result["riskRequirements"][0]["evidence"]
    assert text[evidence["start"] : evidence["end"]] == evidence["text"]


def test_job_evaluation_applies_user_elite_school_policy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs/evaluate",
        json={
            "jobText": "本科以上学历，985、211院校优先。",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
            "eliteSchoolAction": "use_default_materials",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["hasRiskSignals"] is True
    assert result["decision"]["shouldDeliver"] is True
    assert result["decision"]["materialStrategy"] == "default"


def test_negated_elite_school_text_does_not_apply_policy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs/evaluate",
        json={
            "jobText": "不要求985、211背景，重视项目能力。",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
            "eliteSchoolAction": "use_default_materials",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["hasRiskSignals"] is False
    assert result["decision"]["materialStrategy"] == "custom"
