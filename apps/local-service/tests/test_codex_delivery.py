import pytest
from conftest import authenticate
from fastapi.testclient import TestClient

from job_search_assistant.codex_delivery.eligibility import (
    education_block_reason,
    incomplete_title_reason,
    missing_linux_evidence_reason,
)
from job_search_assistant.main import create_app


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


def test_run_list_shows_only_latest_20_for_current_user(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.post("/v1/codex-delivery/configs", json=config_payload())
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    run_ids = [
        client.post("/v1/agent/runs", json={}, headers=agent_headers(key)).json()["id"]
        for _ in range(22)
    ]
    listed = client.get("/v1/codex-delivery/runs").json()["items"]
    assert [run["id"] for run in listed] == list(reversed(run_ids[-20:]))
    assert client.get(f"/v1/codex-delivery/runs/{run_ids[0]}").status_code == 200


def test_other_user_config_update_cannot_change_own_default_or_select_foreign_resume(
    tmp_path,
) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    first_config = client.post("/v1/codex-delivery/configs", json=config_payload()).json()
    resume = client.post(
        "/v1/library/resumes", json={"name": "首个用户简历", "data": {"content": "测试"}}
    ).json()

    authenticate(client, "codex-isolation-second", "password123")
    own_config = client.post("/v1/codex-delivery/configs", json=config_payload()).json()
    forbidden = client.put(
        f"/v1/codex-delivery/configs/{first_config['id']}",
        json=config_payload(name="越权设默认", isDefault=True),
    )
    assert forbidden.status_code == 404
    assert client.get("/v1/codex-delivery/configs").json()["items"][0]["id"] == own_config["id"]
    assert client.post(
        "/v1/codex-delivery/configs", json=config_payload(resumeId=resume["id"])
    ).status_code == 422


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
    assert any(
        "硕士" in reason and "本科" in reason
        for reason in analyzed.json()["decisionReasons"]
    )


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


@pytest.mark.parametrize(
    ("profile", "resume_data", "required", "expected"),
    [
        ({}, {"rawText": "教育经历\n北京城市学院｜计算机科学与技术·本科｜2012—2016"}, "本科", None),
        (
            {},
            {"rawText": "教育背景\n北京城市学院｜本科\n工作经历\n指导硕士项目"},
            "硕士",
            "岗位要求硕士及以上学历，所选简历为本科",
        ),
        ({}, {"educations": [{"degree": "本科"}]}, "本科", None),
        ({}, {"education": "本科"}, "硕士", "岗位要求硕士及以上学历，所选简历为本科"),
        (
            {"education": "本科"},
            {"education": "硕士"},
            "硕士",
            "岗位要求硕士及以上学历，个人档案为本科",
        ),
        (
            {},
            {"rawText": "项目经历\n硕士招聘系统开发"},
            "本科",
            "岗位要求本科及以上学历，但个人档案和所选简历均未填写可核验学历",
        ),
        (
            {},
            {"confirmationStatus": "pending", "education": "本科"},
            "本科",
            "岗位要求本科及以上学历，但个人档案和所选简历均未填写可核验学历",
        ),
    ],
)
def test_education_gate_uses_selected_resume_only_when_profile_missing(
    profile, resume_data, required, expected
) -> None:
    assert (
        education_block_reason({"education": required}, profile, {"data": resume_data}) == expected
    )


@pytest.mark.parametrize(
    ("required", "select_resume", "should_deliver"),
    [("本科", True, True), ("硕士", True, False), ("本科", False, False)],
)
def test_analyze_uses_run_selected_resume_education(
    tmp_path, required, select_resume, should_deliver
) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put("/v1/profile", json={"data": {"summary": "真实 Python Agent 项目"}})
    resume = client.post(
        "/v1/library/resumes",
        json={
            "name": "本次选中简历",
            "data": {"rawText": "教育经历\n北京城市学院｜计算机科学与技术·本科｜2012—2016"},
        },
    ).json()
    other_resume = client.post(
        "/v1/library/resumes",
        json={"name": "其他简历", "data": {"education": "博士"}},
    ).json()
    config = client.post(
        "/v1/codex-delivery/configs",
        json=config_payload(resumeId=resume["id"] if select_resume else None),
    ).json()
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    # Later config edits must not change the resume selected by this run.
    client.put(
        f"/v1/codex-delivery/configs/{config['id']}",
        json=config_payload(resumeId=other_resume["id"]),
    )
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "resume-education-fallback",
            "snapshot": {
                "title": "Python Agent 工程师",
                "companyName": "示例科技",
                "description": "负责 Python Agent 开发",
                "education": required,
                "skills": ["Python", "Agent"],
            },
        },
        headers=headers,
    ).json()
    analyzed = client.post(f"/v1/agent/runs/{run_id}/jobs/{step['id']}/analyze", headers=headers)
    assert analyzed.status_code == 200
    assert analyzed.json()["shouldDeliver"] is should_deliver
    assert analyzed.json()["match"]["decision"]["shouldDeliver"] is should_deliver
    if required == "硕士":
        assert "岗位要求硕士及以上学历，所选简历为本科" in analyzed.json()["decisionReasons"]
    prepared = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/prepare",
        json={
            "platformJobId": "resume-education-fallback",
            "observedTitle": "Python Agent 工程师",
            "observedCompanyName": "示例科技",
        },
        headers=headers,
    )
    assert prepared.status_code == (200 if should_deliver else 409)
    if should_deliver:
        assert prepared.json()["status"] == "opening_chat"
    # Fallback is read-only; it must not silently rewrite the user's profile.
    assert "education" not in client.get("/v1/agent/context", headers=headers).json()["profile"]


def test_incomplete_phone_title_cannot_be_sent() -> None:
    assert incomplete_title_reason({"title": "AI 智能体工程师（医疗方向"})
    assert incomplete_title_reason({"title": "AI Agent 工程师..."})
    assert incomplete_title_reason({"title": "AI Agent 工程师（医疗方向）"}) is None


def test_required_linux_experience_needs_user_evidence() -> None:
    snapshot = {"description": "任职要求：有Linux环境使用经验，熟悉Python。"}
    assert missing_linux_evidence_reason(snapshot, [{"skills": ["Python", "RAG"]}])
    assert missing_linux_evidence_reason(snapshot, [{"skills": ["Python", "Linux"]}]) is None
    assert missing_linux_evidence_reason(
        {"description": "有Linux环境使用经验者优先。"}, []
    ) is None


def test_required_linux_gap_blocks_codex_delivery_even_with_high_similarity(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put("/v1/profile", json={"data": {"summary": "有 Python Agent 与 RAG 项目经验"}})
    client.post("/v1/codex-delivery/configs", json=config_payload())
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "linux-required",
            "snapshot": {
                "title": "AI Agent 工程师",
                "companyName": "示例科技",
                "description": "负责 Agent 和 RAG 开发。任职要求：有Linux环境使用经验。",
                "skills": ["Python", "RAG"],
            },
        },
        headers=headers,
    ).json()
    analyzed = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["shouldDeliver"] is False
    assert any("Linux" in reason for reason in analyzed.json()["decisionReasons"])


def test_codex_flow_blocks_below_matching_threshold(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.post(
        "/v1/codex-delivery/configs",
        json=config_payload(minimumScore=100, minimumCustomizationConfidence=100),
    )
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "weak-evidence",
            "snapshot": {
                "title": "Go 工程师",
                "companyName": "示例公司",
                "description": "负责 Go 后端开发",
            },
        },
        headers=headers,
    ).json()
    analyzed = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["shouldDeliver"] is False
    assert any("阈值" in reason for reason in analyzed.json()["decisionReasons"])


def test_phone_flow_reuses_pc_snapshot_greeting_and_delivery_records(tmp_path) -> None:
    generated_greeting = "您好，我做过真实的 Python Agent 项目，期待交流岗位需求。"

    class GreetingSpy:
        def __init__(self) -> None:
            self.contexts: list[dict] = []

        def generate(self, context: dict, model_record_id=None, *, user_id: int = 1) -> dict:
            self.contexts.append(context)
            return {"greeting": generated_greeting}

    greeting_generator = GreetingSpy()
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", greeting_generator=greeting_generator)
    )
    client.put(
        "/v1/profile",
        json={"data": {"education": "学历：本科", "summary": "有真实 Python Agent 项目"}},
    )
    client.post("/v1/codex-delivery/configs", json=config_payload())
    key = client.post("/v1/agent-keys", json={"name": "Codex"}).json()["plaintext"]
    headers = agent_headers(key)
    run_id = client.post("/v1/agent/runs", json={}, headers=headers).json()["id"]
    step = client.post(
        f"/v1/agent/runs/{run_id}/jobs/capture",
        json={
            "platformJobId": "visible-fingerprint-1",
            "snapshot": {
                "title": "Python Agent 工程师",
                "companyName": "测试科技",
                "description": "负责 Python Agent 开发，要求本科及以上学历。",
                "education": "本科",
                "skills": ["Python", "Agent"],
            },
        },
        headers=headers,
    ).json()
    snapshot_id = step["snapshot"]["pcSnapshotId"]
    jobs = client.get("/v1/jobs").json()["items"]
    assert any(job["id"] == snapshot_id and job["source"] == "codex-phone" for job in jobs)

    analyzed = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["greeting"] == generated_greeting
    assert greeting_generator.contexts[0]["profile"]["education"] == "学历：本科"
    assert greeting_generator.contexts[0]["job"]["title"] == "Python Agent 工程师"
    saved_job = next(
        job for job in client.get("/v1/jobs").json()["items"] if job["id"] == snapshot_id
    )
    assert saved_job["generatedGreeting"] == analyzed.json()["greeting"]

    prepared = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/prepare",
        json={
            "platformJobId": "visible-fingerprint-1",
            "observedTitle": "Python Agent 工程师",
            "observedCompanyName": "测试科技",
        },
        headers=headers,
    )
    assert prepared.status_code == 200
    result = client.post(
        f"/v1/agent/runs/{run_id}/jobs/{step['id']}/result",
        json={
            "outcome": "delivered",
            "idempotencyKey": "phone-flow-greeting-sent-1",
            "evidence": {
                "messageVisible": True,
                "inputMethod": "first_common_phrase",
                "sentText": "您好，我对这个岗位很感兴趣，期待与您沟通。",
            },
        },
        headers=headers,
    )
    assert result.status_code == 200
    saved_job = next(
        job for job in client.get("/v1/jobs").json()["items"] if job["id"] == snapshot_id
    )
    assert saved_job["hasCommunicated"] is True
    delivery = client.get("/v1/deliveries").json()["items"][0]
    assert delivery["status"] == "delivered"
    assert delivery["greetingText"] == "您好，我对这个岗位很感兴趣，期待与您沟通。"
    assert delivery["metadata"]["source"] == "codex-phone"
    assert delivery["metadata"]["evidence"]["inputMethod"] == "first_common_phrase"
