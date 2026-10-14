from conftest import authenticate
from fastapi.testclient import TestClient

from job_search_assistant.main import create_app
from job_search_assistant.codex_delivery.eligibility import education_block_reason


def config_payload(**overrides: object) -> dict:
    payload = {
        "name": "Codex 默认配置",
        "isDefault": True,
        "enabled": True,
        "sourceTabs": ["推荐", "最新"],
        "jobIntentions": [],
        "keywords": ["Python", "后端"],
        "cityCode": "101280600",
        "cityName": "深圳",
        "experience": [{"label": "3-5年", "code": "104"}],
        "degree": [{"label": "本科", "code": "206"}],
        "companyScale": [{"label": "100-499人", "code": "303"}],
        "bossActivity": {"label": "今日活跃", "code": "today"},
        "salaryMode": "preset",
        "salaryCode": "15-25K",
        "salaryMinK": None,
        "salaryMaxK": None,
        "benefits": [{"label": "周末双休"}],
        "financing": [],
        "industries": [{"label": "计算机软件"}],
        "recommendedTags": [],
        "targetDeliveryCount": 1,
        "maxScanCount": 10,
        "intervalSeconds": 2,
        "minimumScore": 0,
        "minimumCustomizationConfidence": 0,
        "resumeId": None,
        "sendResume": False,
        "greetingStrategy": "custom",
        "fallbackGreeting": "您好，希望进一步沟通。",
        "confirmationMode": "automatic",
        "stopOnUncertain": True,
    }
    payload.update(overrides)
    return payload


def agent_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_agent_key_config_and_single_job_run_are_isolated(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    config = client.post("/v1/codex-delivery/configs", json=config_payload())
    assert config.status_code == 201
    assert config.json()["sourceTabs"] == ["推荐", "最新"]

    key_response = client.post(
        "/v1/agent-keys",
        json={"name": "本机 Codex", "scopes": ["agent:read", "agent:run"], "expiresInDays": 30},
    )
    assert key_response.status_code == 201
    plaintext = key_response.json()["plaintext"]
    assert plaintext.startswith("jsa_agent_")
    assert "plaintext" not in client.get("/v1/agent-keys").text

    headers = agent_headers(plaintext)
    assert client.get("/v1/agent/me", headers=headers).status_code == 200
    context = client.get("/v1/agent/context", headers=headers)
    assert context.status_code == 200
    assert set(context.json()) == {"profile", "projects", "resumes", "rules", "targets"}
    assert client.get("/v1/agent/configs/default", headers=headers).json()["cityName"] == "深圳"

    run_response = client.post("/v1/agent/runs", json={}, headers=headers)
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    snapshot = {
        "title": "Python 后端工程师",
        "companyName": "示例科技",
        "description": "负责 Python 服务端开发和 API 设计",
        "skills": ["Python", "FastAPI"],
        "salaryText": "20-30K",
        "recruiterActiveText": "今日活跃",
    }
    capture = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "boss-1001",
            "sourceTab": "最新",
            "listPosition": 1,
            "snapshot": snapshot,
        },
        headers=headers,
    )
    assert capture.status_code == 200
    step_id = capture.json()["id"]

    analyzed = client.post(f"/v1/agent/runs/{run_id}/jobs/{step_id}/analyze", headers=headers)
    assert analyzed.status_code == 200
    assert analyzed.json()["shouldDeliver"] is True
    assert "Python 后端工程师" in analyzed.json()["greeting"]

    # A second job cannot overtake the current one, and sending needs a
    # fresh identity check against the captured detail page.
    blocked_next = client.post(
        f"/v1/agent/runs/{run_id}/jobs/check",
        json={"platformJobId": "boss-1002", "sourceTab": "最新"},
        headers=headers,
    )
    assert blocked_next.status_code == 409
    mismatched = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/prepare",
        json={
            "platformJobId": "boss-1001",
            "observedTitle": "其他岗位",
            "observedCompanyName": "示例科技",
        },
        headers=headers,
    )
    assert mismatched.status_code == 409

    prepare = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/prepare",
        json={
            "platformJobId": "boss-1001",
            "observedTitle": "Python 后端工程师",
            "observedCompanyName": "示例科技",
        },
        headers=headers,
    )
    assert prepare.status_code == 200
    assert prepare.json()["status"] == "opening_chat"

    no_evidence = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/result",
        json={"outcome": "delivered", "idempotencyKey": "delivery-boss-1001"},
        headers=headers,
    )
    assert no_evidence.status_code == 409

    result = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/result",
        json={
            "outcome": "delivered",
            "idempotencyKey": "delivery-boss-1001",
            "evidence": {"messageVisible": True},
        },
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["run"]["status"] == "completed"
    assert result.json()["run"]["deliveredCount"] == 1

    repeated = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/result",
        json={
            "outcome": "delivered",
            "idempotencyKey": "delivery-boss-1001",
            "evidence": {"messageVisible": True},
        },
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["run"]["deliveredCount"] == 1

    changed_outcome = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step_id}/result",
        json={
            "outcome": "failed",
            "idempotencyKey": "delivery-boss-1001",
            "evidence": {},
        },
        headers=headers,
    )
    assert changed_outcome.status_code == 409

    # The isolated workflow must not create legacy automation runs.
    assert client.get("/v1/automation/runs").json()["items"] == []


def test_revoked_and_read_only_agent_keys_are_rejected(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.post("/v1/codex-delivery/configs", json=config_payload())

    read_only = client.post(
        "/v1/agent-keys",
        json={"name": "只读", "scopes": ["agent:read"], "expiresInDays": 30},
    ).json()
    headers = agent_headers(read_only["plaintext"])
    assert client.get("/v1/agent/me", headers=headers).status_code == 200
    assert client.post("/v1/agent/runs", json={}, headers=headers).status_code == 401

    revoked = client.delete(f"/v1/agent-keys/{read_only['key']['id']}")
    assert revoked.status_code == 200
    assert client.get("/v1/agent/me", headers=headers).status_code == 401


def test_config_validates_plan_and_custom_salary(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    invalid_plan = client.post(
        "/v1/codex-delivery/configs",
        json=config_payload(targetDeliveryCount=5, maxScanCount=2),
    )
    assert invalid_plan.status_code == 422

    invalid_salary = client.post(
        "/v1/codex-delivery/configs",
        json=config_payload(salaryMode="custom", salaryMinK=30, salaryMaxK=20),
    )
    assert invalid_salary.status_code == 422


def test_codex_configs_keys_and_runs_are_isolated_per_user(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    config = client.post("/v1/codex-delivery/configs", json=config_payload()).json()
    key = client.post(
        "/v1/agent-keys",
        json={"name": "首个用户", "scopes": ["agent:read", "agent:run"]},
    ).json()["plaintext"]
    run = client.post("/v1/agent/runs", json={}, headers=agent_headers(key)).json()

    authenticate(client, "codex-second-user", "password123")
    assert client.get("/v1/codex-delivery/configs").json()["items"] == []
    assert client.get("/v1/agent-keys").json()["items"] == []
    assert client.get(f"/v1/codex-delivery/runs/{run['id']}").status_code == 404
    assert (
        client.put(
            f"/v1/codex-delivery/configs/{config['id']}", json=config_payload(name="越权修改")
        ).status_code
        == 404
    )


def test_uncertain_result_stops_run_without_recording_delivery(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.post("/v1/codex-delivery/configs", json=config_payload())
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "uncertain-1",
            "snapshot": {
                "title": "测试工程师",
                "companyName": "示例公司",
                "description": "Python 测试开发",
            },
        },
        headers=headers,
    ).json()
    result = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/result",
        json={
            "outcome": "uncertain",
            "idempotencyKey": "uncertain-job-1",
            "errorMessage": "无法确认发送状态",
        },
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["run"]["status"] == "uncertain"
    assert result.json()["run"]["deliveredCount"] == 0
    assert (
        client.post(
            f"/v1/agent/runs/{run_id}/jobs/check",
            json={"platformJobId": "another-job"},
            headers=headers,
        ).status_code
        == 409
    )


def test_education_requirement_blocks_delivery_despite_high_similarity(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put(
        "/v1/profile",
        json={"data": {"educations": [{"degree": "本科"}], "education": "学历：本科"}},
    )
    client.post("/v1/codex-delivery/configs", json=config_payload())
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "master-degree-required",
            "snapshot": {
                "title": "AI Agent 工程师",
                "companyName": "示例公司",
                "description": "熟悉 Python 和 Agent 开发，要求硕士及以上学历。",
                "education": "硕士",
                "skills": ["Python", "Agent"],
            },
        },
        headers=headers,
    ).json()
    analyzed = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["shouldDeliver"] is False
    assert analyzed.json()["match"]["decision"]["shouldDeliver"] is False
    assert any("硕士" in reason and "本科" in reason for reason in analyzed.json()["decisionReasons"])


def test_education_gate_ignores_preferences_and_accepts_met_requirements() -> None:
    profile = {"educations": [{"degree": "本科"}]}
    assert education_block_reason(
        {"education": "本科", "description": "硕士优先"}, profile
    ) is None
    assert education_block_reason(
        {"description": "本科及以上学历，硕士优先"}, profile
    ) is None
    assert education_block_reason(
        {"education": "硕士", "description": "负责 Agent 开发"}, profile
    ) == "岗位要求硕士及以上学历，个人档案为本科"
