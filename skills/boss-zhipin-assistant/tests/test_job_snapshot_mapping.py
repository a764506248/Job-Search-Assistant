import os
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))
os.environ.setdefault("BOSS_PROFILE_FILE", str(SKILL_DIR / "user_profile.example.json"))

from scripts import local_service_client


def _current_jd(surface: dict[str, object]) -> dict[str, object]:
    return {
        "jobId": "job-1",
        "title": "AI Agent 工程师",
        "company": "示例公司",
        "jd_text": "负责 Agent 与 RAG 应用开发",
        "jd_full": {
            "job_title": "AI Agent 工程师",
            "jd_text": "负责 Agent 与 RAG 应用开发",
        },
        "surface_info": surface,
    }


def test_analyze_plan_maps_company_size_from_surface(monkeypatch) -> None:
    captured = {}

    def fake_request(path, method="GET", payload=None, timeout=30):
        captured.update({"path": path, "method": method, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(local_service_client, "_json_request", fake_request)

    local_service_client.analyze_and_plan_job(
        _current_jd({"company_size": "100-499人"})
    )

    assert captured["payload"]["job"]["companySize"] == "100-499人"


def test_analyze_plan_supports_legacy_scale_field(monkeypatch) -> None:
    captured = {}

    def fake_request(path, method="GET", payload=None, timeout=30):
        captured.update({"payload": payload})
        return {"ok": True}

    monkeypatch.setattr(local_service_client, "_json_request", fake_request)

    local_service_client.analyze_and_plan_job(_current_jd({"scale": "1000-9999人"}))

    assert captured["payload"]["job"]["companySize"] == "1000-9999人"
