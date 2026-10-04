import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from job_search_assistant.main import create_app
from job_search_assistant.repositories import AutomationRepository


class MaterialPreviewEmbedder:
    model = "test/material-preview"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(text.count("RAG")), 1.0, 0.5] for text in texts]


class FakeMaterialPreviewGenerator:
    def __init__(self) -> None:
        self.context: dict[str, object] = {}

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        self.context = context
        return {
            "modelRecordId": 7,
            "modelName": "测试模型",
            "modelId": "test-model",
            "greeting": "您好，我有 RAG 与 Agent 项目经验，与岗位需求匹配。",
            "resume": {
                "headline": "AI Agent 工程师",
                "summary": ["具备 RAG 项目经验"],
                "skills": ["Python", "RAG"],
                "projects": ["企业知识库：负责 RAG 检索"],
                "workExperience": ["示例公司 · AI 工程师"],
                "education": ["示例大学 · 本科"],
                "optimizationNotes": ["优先展示 RAG 项目"],
            },
        }


class FakeGreetingGenerator:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.contexts: list[dict[str, object]] = []

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        self.contexts.append(context)
        if self.error:
            raise RuntimeError(self.error)
        return {
            "modelRecordId": 9,
            "modelName": "问候语测试模型",
            "modelId": "test-greeting",
            "greeting": "您好，我有 RAG 与 Agent 项目经验，希望进一步沟通岗位需求。",
        }


class FakeJobAnalysisGenerator:
    def __init__(self) -> None:
        self.context: dict[str, object] = {}
        self.model_record_id: int | None = None

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        self.context = context
        self.model_record_id = model_record_id
        return {
            "modelRecordId": 11,
            "modelName": "职位分析测试模型",
            "modelId": "test-analysis",
            "summary": "候选人的 RAG 经历与岗位核心需求匹配。",
            "strengths": ["企业知识库项目可证明 RAG 实践经验"],
            "gaps": ["Agent 线上稳定性经验需要进一步核实"],
            "recommendations": ["面试前准备知识库项目的效果数据"],
            "interviewQuestions": ["如何评估 RAG 检索质量？"],
        }


class RecordingBrowserHub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def status(self) -> dict[str, object]:
        return {
            "connected": True,
            "paired": True,
            "protocolVersion": "1.0",
            "extensionVersion": "0.4.11-test",
        }

    async def dispatch(
        self,
        *,
        run_id: int,
        action: str,
        payload: dict[str, object],
        deadline_ms: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "runId": run_id,
                "action": action,
                "payload": payload,
                "deadlineMs": deadline_ms,
            }
        )
        return {
            "requestId": "browser-result-1",
            "status": "success",
            "evidence": {"messageBubbleObserved": True},
        }


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_setup_status_reports_actionable_first_run_checks(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )

    response = client.get("/v1/setup/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"] == "blocked"
    assert payload["total"] == 10
    checks = {item["key"]: item for item in payload["checks"]}
    assert checks["local-service"]["status"] == "ready"
    assert checks["model"]["status"] == "blocked"
    assert checks["resume"]["actionPath"] == "/resumes"
    assert checks["kimi-webbridge"]["status"] == "blocked"
    assert checks["boss-login"]["status"] == "pending"
    assert checks["skill-version"]["status"] == "ready"
    assert checks["skill-version"]["blocking"] is False
    assert checks["automation-runner"]["status"] == "blocked"
    assert payload["checkedAt"]


def test_browser_probe_is_persisted_and_updates_setup_checks(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    client = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))

    saved = client.post(
        "/v1/setup/browser/probe",
        json={
            "webbridgeRunning": True,
            "kimiExtensionConnected": True,
            "projectExtensionReady": True,
            "bossLoggedIn": True,
            "skillVersion": "5.10.0",
            "source": "manual",
        },
    )

    assert saved.status_code == 200
    assert saved.json()["checkedAt"]
    restarted = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))
    checks = {
        item["key"]: item for item in restarted.get("/v1/setup/status").json()["checks"]
    }
    assert checks["kimi-webbridge"]["status"] == "blocked"
    assert checks["project-extension"]["status"] == "ready"
    assert checks["boss-login"]["status"] == "ready"
    assert checks["skill-version"]["status"] == "ready"
    assert checks["skill-version"]["blocking"] is False


def test_setup_test_run_never_executes_browser_actions(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )

    response = client.post("/v1/setup/test-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "dry-run"
    assert payload["browserActionsExecuted"] is False
    assert payload["ok"] is False
    assert "大模型连接" in payload["blockingChecks"]
    assert "未通过" in payload["message"]


def test_automation_run_api_blocks_start_when_setup_is_incomplete(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 12,
            "config": {
                "searchKeywords": ["AI Agent"],
                "plannedJobs": [
                    {
                        "jobId": "job-1",
                        "url": "https://www.zhipin.com/job_detail/job-1.html",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                        "salaryText": "25-35K",
                        "greeting": "您好，希望进一步沟通。",
                    }
                ],
            },
        },
    )

    assert created.status_code == 201
    run_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    started = client.post(
        f"/v1/automation/runs/{run_id}/start",
        json={"selectedJobIds": ["job-1"]},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "blocked"
    assert "大模型连接" in started.json()["stopReason"]
    listing = client.get("/v1/automation/runs").json()["items"]
    assert listing[0]["id"] == run_id
    events = client.get(f"/v1/automation/runs/{run_id}/events").json()["items"]
    assert [event["eventType"] for event in events] == [
        "run-created",
        "plan-confirmed",
        "status-changed",
        "status-changed",
    ]


def test_automation_run_requires_explicit_job_confirmation_before_running(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    created = client.post(
        "/v1/automation/runs",
        json={"targetCount": 5, "config": {"plannedJobs": []}},
    )

    started = client.post(f"/v1/automation/runs/{created.json()['id']}/start")

    assert started.status_code == 422
    assert started.json()["detail"] == "请先确认至少一个待投企业"
    assert client.get(f"/v1/automation/runs/{created.json()['id']}").json()["status"] == "draft"


def test_automation_run_starts_only_with_user_confirmed_jobs(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    jobs = [
        {
            "jobId": "job-1",
            "url": "https://www.zhipin.com/job_detail/job-1.html",
            "title": "AI Agent 工程师",
            "companyName": "甲公司",
            "salaryText": "25-35K",
            "greeting": "您好，想沟通岗位一。",
        },
        {
            "jobId": "job-2",
            "url": "https://www.zhipin.com/job_detail/job-2.html",
            "title": "RAG 工程师",
            "companyName": "乙公司",
            "salaryText": "25-35K",
            "greeting": "您好，想沟通岗位二。",
        },
    ]
    created = client.post(
        "/v1/automation/runs",
        json={"targetCount": 2, "config": {"plannedJobs": jobs}},
    ).json()

    started = client.post(
        f"/v1/automation/runs/{created['id']}/start",
        json={"selectedJobIds": ["job-2"]},
    )

    assert started.status_code == 200
    payload = started.json()
    assert payload["targetCount"] == 1
    assert [job["jobId"] for job in payload["configSnapshot"]["plannedJobs"]] == [
        "job-2"
    ]
    confirmation = payload["configSnapshot"]["planConfirmation"]
    assert confirmation["status"] == "confirmed"
    assert confirmation["selectedJobIds"] == ["job-2"]
    assert "approvalToken" not in confirmation
    events = client.get(
        f"/v1/automation/runs/{created['id']}/events"
    ).json()["items"]
    assert [event["eventType"] for event in events] == [
        "run-created",
        "plan-confirmed",
        "status-changed",
        "status-changed",
    ]
    assert events[1]["payload"]["companies"] == ["乙公司"]
    assert "approvalToken" not in json.dumps(events, ensure_ascii=False)


def test_retry_creates_new_run_for_only_unsuccessful_jobs_and_skips_completed_send_steps(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    client = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))
    jobs = [
        {
            "jobId": "job-success",
            "url": "https://www.zhipin.com/job_detail/job-success.html",
            "title": "AI Agent 工程师",
            "companyName": "甲公司",
            "salaryText": "25-35K",
            "greeting": "您好，想沟通岗位一。",
        },
        {
            "jobId": "job-retry",
            "url": "https://www.zhipin.com/job_detail/job-retry.html",
            "title": "RAG 工程师",
            "companyName": "乙公司",
            "salaryText": "25-35K",
            "greeting": "您好，想沟通岗位二。",
        },
    ]
    source = client.post(
        "/v1/automation/runs",
        json={"targetCount": 2, "config": {"plannedJobs": jobs}},
    ).json()
    started = client.post(
        f"/v1/automation/runs/{source['id']}/start",
        json={"selectedJobIds": ["job-success", "job-retry"]},
    ).json()
    assert started["status"] == "blocked"

    repository = AutomationRepository(database_path)
    repository.record_progress(source["id"], "job-success", "success", "投递已确认")
    greeting_action, _ = repository.claim_action(
        source["id"], "job-retry", "send_greeting"
    )
    repository.finish_action(greeting_action["idempotency_key"], succeeded=True)
    repository.record_progress(source["id"], "job-retry", "failure", "简历发送失败")

    response = client.post(f"/v1/automation/runs/{source['id']}/retry")

    assert response.status_code == 200
    retried = response.json()
    assert retried["id"] != source["id"]
    assert retried["configSnapshot"]["retryOfRunId"] == source["id"]
    assert [
        job["jobId"] for job in retried["configSnapshot"]["plannedJobs"]
    ] == ["job-retry"]
    assert retried["configSnapshot"]["plannedJobs"][0]["retrySkipGreeting"] is True
    assert retried["configSnapshot"]["planConfirmation"]["status"] == "confirmed"
    events = client.get(f"/v1/automation/runs/{retried['id']}/events").json()["items"]
    assert "retry-created" in [event["eventType"] for event in events]


def test_retry_rejects_run_without_unsuccessful_jobs(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    client = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))
    job = {
        "jobId": "job-success",
        "url": "https://www.zhipin.com/job_detail/job-success.html",
        "title": "AI Agent 工程师",
        "companyName": "甲公司",
        "salaryText": "25-35K",
        "greeting": "您好，想进一步沟通。",
    }
    source = client.post(
        "/v1/automation/runs",
        json={"targetCount": 1, "config": {"plannedJobs": [job]}},
    ).json()
    client.post(
        f"/v1/automation/runs/{source['id']}/start",
        json={"selectedJobIds": ["job-success"]},
    )
    AutomationRepository(database_path).record_progress(
        source["id"], "job-success", "success", "投递已确认"
    )

    response = client.post(f"/v1/automation/runs/{source['id']}/retry")

    assert response.status_code == 409
    assert response.json()["detail"] == "没有失败或未完成的岗位可以重试"


def test_send_greeting_requires_confirmed_plan_and_dispatches_server_evidence(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    hub = RecordingBrowserHub()
    client = TestClient(
        create_app(
            database_path,
            embedder=MaterialPreviewEmbedder(),
            browser_hub=hub,
        )
    )
    greeting = "您好，想进一步沟通这个岗位。"
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "plannedJobs": [
                    {
                        "jobId": "approved-job",
                        "url": "https://www.zhipin.com/job_detail/approved-job.html",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                        "salaryText": "25-35K",
                        "greeting": greeting,
                    }
                ]
            },
        },
    ).json()
    client.post(
        f"/v1/automation/runs/{created['id']}/start",
        json={"selectedJobIds": ["approved-job"]},
    )
    confirmed = client.get(f"/v1/automation/runs/{created['id']}").json()
    assert "approvalToken" not in json.dumps(confirmed, ensure_ascii=False)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE automation_runs SET status = 'running', runner_id = NULL WHERE id = ?",
            (created["id"],),
        )
    claim = client.post(
        "/v1/automation/runner/claim", json={"runnerId": "test-runner"}
    ).json()
    token = claim["approvalToken"]
    assert token
    assert "approvalToken" not in json.dumps(claim["run"], ensure_ascii=False)
    assert "approvalToken" not in client.get(
        f"/v1/automation/runs/{created['id']}"
    ).text
    assert "approvalToken" not in client.get("/v1/automation/runs").text
    heartbeat = client.post(
        f"/v1/automation/runs/{created['id']}/heartbeat",
        json={"runnerId": "test-runner"},
    )
    assert "approvalToken" not in heartbeat.text

    base_payload = {
        "runnerId": "test-runner",
        "jobId": "approved-job",
        "action": "send_greeting",
        "payload": {
            "expectedJobId": "approved-job",
            "expectedTitle": "AI Agent 工程师",
            "expectedCompany": "示例公司",
            "text": greeting,
        },
        "deadlineMs": 60_000,
    }
    forged = json.loads(json.dumps(base_payload, ensure_ascii=False))
    forged["payload"]["planConfirmed"] = True
    missing_token = client.post(
        f"/v1/automation/runs/{created['id']}/browser-action",
        json=forged,
    )
    assert missing_token.status_code == 409
    assert not hub.calls

    changed_text = json.loads(json.dumps(base_payload, ensure_ascii=False))
    changed_text["payload"].update(
        {"approvalToken": token, "text": "这不是用户确认的问候语"}
    )
    mismatch = client.post(
        f"/v1/automation/runs/{created['id']}/browser-action",
        json=changed_text,
    )
    assert mismatch.status_code == 409
    assert not hub.calls

    approved = json.loads(json.dumps(base_payload, ensure_ascii=False))
    approved["payload"].update(
        {
            "approvalToken": token,
            "userConfirmed": False,
            "planConfirmed": False,
        }
    )
    response = client.post(
        f"/v1/automation/runs/{created['id']}/browser-action",
        json=approved,
    )

    assert response.status_code == 200
    assert len(hub.calls) == 1
    dispatched = hub.calls[0]["payload"]
    assert dispatched["planConfirmed"] is True
    assert "approvalToken" not in dispatched
    assert "userConfirmed" not in dispatched
    with sqlite3.connect(database_path) as connection:
        actions = connection.execute(
            "SELECT COUNT(*) FROM automation_actions WHERE run_id = ?",
            (created["id"],),
        ).fetchone()[0]
    assert actions == 1


def test_automation_run_rejects_empty_confirmed_plan(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "plannedJobs": [
                    {
                        "jobId": "job-1",
                        "url": "https://www.zhipin.com/job_detail/job-1.html",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                    }
                ]
            },
        },
    ).json()

    response = client.post(
        f"/v1/automation/runs/{created['id']}/start",
        json={"selectedJobIds": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "selectedJobIds"]
    assert client.get(f"/v1/automation/runs/{created['id']}").json()["status"] == "draft"


def test_old_draft_plan_is_normalized_and_rejected_before_confirmation(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    client = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))
    client.put("/v1/profile", json={"data": {"minimumSalaryK": 20}})
    client.post(
        "/v1/library/rules",
        json={
            "name": "价格",
            "data": {
                "pattern": "18k-35k不在这个价格区间的禁止投递",
                "action": "block_delivery",
            },
        },
    )
    raw_salaries = [
        "\ue034\ue037-\ue036\ue031K·\ue032\ue036薪",
        "\ue035\ue031-\ue037\ue031K·\ue032\ue036薪",
    ]
    jobs = [
        {
            "jobId": "legacy-job-1",
            "url": "https://www.zhipin.com/job_detail/legacy-job-1.html",
            "title": "AI Agent 工程师",
            "companyName": "甲科技",
            "salaryText": raw_salaries[0],
            "greeting": "您好，希望进一步沟通。",
        },
        {
            "jobId": "legacy-job-2",
            "url": "https://www.zhipin.com/job_detail/legacy-job-2.html",
            "title": "RAG 工程师",
            "companyName": "乙智能",
            "salaryText": raw_salaries[1],
            "greeting": "您好，希望进一步沟通。",
        },
    ]
    created = client.post(
        "/v1/automation/runs",
        json={"targetCount": 2, "config": {"plannedJobs": jobs}},
    ).json()
    run_id = created["id"]

    # Simulate a task persisted before salary normalization was introduced.
    with sqlite3.connect(database_path) as connection:
        raw_config = json.loads(
            connection.execute(
                "SELECT config_snapshot_json FROM automation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()[0]
        )
        raw_config["plannedJobs"][0]["salaryText"] = raw_salaries[0]
        raw_config["plannedJobs"][1]["salaryText"] = raw_salaries[1]
        connection.execute(
            "UPDATE automation_runs SET config_snapshot_json = ? WHERE id = ?",
            (json.dumps(raw_config, ensure_ascii=False), run_id),
        )

    run_output = client.get(f"/v1/automation/runs/{run_id}").json()
    list_output = client.get("/v1/automation/runs").json()["items"][0]
    report_output = client.get(f"/v1/automation/runs/{run_id}/report").json()["run"]
    for output in (run_output, list_output, report_output):
        assert [
            job["salaryText"] for job in output["configSnapshot"]["plannedJobs"]
        ] == ["36-50K·15薪", "40-60K·15薪"]

    started = client.post(
        f"/v1/automation/runs/{run_id}/start",
        json={"selectedJobIds": ["legacy-job-1", "legacy-job-2"]},
    )

    assert started.status_code == 422
    assert "薪资策略校验未通过，已阻止启动" in started.json()["detail"]
    assert "36-50K 与规则允许的 18-35K 无交集" in started.json()["detail"]
    assert "40-60K 与规则允许的 18-35K 无交集" in started.json()["detail"]
    unchanged = client.get(f"/v1/automation/runs/{run_id}").json()
    assert unchanged["status"] == "draft"
    assert unchanged["targetCount"] == 2
    events = client.get(f"/v1/automation/runs/{run_id}/events").json()["items"]
    assert [event["eventType"] for event in events] == ["run-created"]
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM automation_actions WHERE run_id = ?", (run_id,)
        ).fetchone()[0] == 0


def test_client_snapshot_cannot_weaken_current_salary_policy(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    client.put("/v1/profile", json={"data": {"minimumSalaryK": 20}})
    current_rule = client.post(
        "/v1/library/rules",
        json={
            "name": "价格",
            "data": {
                "pattern": "18k-35k不在这个价格区间的禁止投递",
                "action": "block_delivery",
            },
        },
    ).json()
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "minimumSalaryK": 0,
                "matchingRules": [],
                "plannedJobs": [
                    {
                        "jobId": "weakened-snapshot-job",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                        "salaryText": "36-40K",
                    }
                ],
            },
        },
    ).json()

    response = client.post(
        f"/v1/automation/runs/{created['id']}/start",
        json={"selectedJobIds": ["weakened-snapshot-job"]},
    )

    assert response.status_code == 422
    assert "36-40K 与规则允许的 18-35K 无交集" in response.json()["detail"]
    assert f"library:{current_rule['id']}" in {
        rule["id"] for rule in client.get("/v1/automation/config").json()["matchingRules"]
    }
    assert client.get(f"/v1/automation/runs/{created['id']}").json()["status"] == "draft"


@pytest.mark.parametrize(
    ("salary_text", "expected_message"),
    [
        (None, "未提供薪资"),
        ("300-500元/天", "不是月薪 K 区间"),
        ("60-150元/时", "不是月薪 K 区间"),
        ("\ue100-\ue101K", "包含无法识别的私有区字符"),
    ],
)
def test_draft_start_fails_closed_for_unverifiable_salary(
    tmp_path, salary_text: str | None, expected_message: str
) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "minimumSalaryK": 20,
                "plannedJobs": [
                    {
                        "jobId": "unsafe-salary-job",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                        "salaryText": salary_text,
                    }
                ],
            },
        },
    ).json()

    response = client.post(
        f"/v1/automation/runs/{created['id']}/start",
        json={"selectedJobIds": ["unsafe-salary-job"]},
    )

    assert response.status_code == 422
    assert expected_message in response.json()["detail"]
    assert client.get(f"/v1/automation/runs/{created['id']}").json()["status"] == "draft"


@pytest.mark.parametrize(
    ("status", "endpoint"),
    [("interrupted", "start"), ("paused", "resume")],
)
def test_restart_and_resume_revalidate_current_plan_salary(
    tmp_path, status: str, endpoint: str
) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    client = TestClient(create_app(database_path, embedder=MaterialPreviewEmbedder()))
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "minimumSalaryK": 20,
                "plannedJobs": [
                    {
                        "jobId": "resume-salary-job",
                        "title": "AI Agent 工程师",
                        "companyName": "示例公司",
                        "salaryText": "15-30K",
                    }
                ],
            },
        },
    ).json()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE automation_runs SET status = ? WHERE id = ?",
            (status, created["id"]),
        )

    response = client.post(f"/v1/automation/runs/{created['id']}/{endpoint}")

    assert response.status_code == 422
    assert "上限 15K 低于最低薪资 20K，无交集" in response.json()["detail"]
    assert client.get(f"/v1/automation/runs/{created['id']}").json()["status"] == status


def test_runner_heartbeat_endpoint_updates_setup_check(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )

    heartbeat = client.post(
        "/v1/automation/runner/heartbeat",
        json={"runnerId": "compose-runner"},
    )
    checks = {
        item["key"]: item for item in client.get("/v1/setup/status").json()["checks"]
    }

    assert heartbeat.status_code == 200
    assert heartbeat.json()["online"] is True
    assert checks["automation-runner"]["status"] == "ready"


def test_extension_error_log_is_stored_locally(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "source": "extension-content",
        "level": "error",
        "event": "job-analysis-failed",
        "message": "Local service request failed: 503",
        "pageUrl": "https://www.zhipin.com/job_detail/example.html",
        "platformJobId": "example",
        "occurredAt": "2026-09-28T09:00:00Z",
    }

    created = client.post("/v1/client-logs", json=payload)
    assert created.status_code == 201
    assert created.json()["id"] == 1

    listing = client.get("/v1/client-logs")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["event"] == "job-analysis-failed"
    assert listing.json()["items"][0]["message"] == payload["message"]


def test_boss_content_script_origin_can_access_local_service(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.options(
        "/v1/jobs/match",
        headers={
            "Origin": "https://www.zhipin.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://www.zhipin.com"
    assert response.headers["access-control-allow-private-network"] == "true"


def test_unrelated_web_origin_cannot_access_local_service(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.options(
        "/v1/jobs/match",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_backend_is_api_only(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    assert client.get("/").status_code == 404
    assert client.get("/models").status_code == 404
    assert client.get("/v1/health").status_code == 200


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
    payload["jobs"][0].update(
        {
            "location": "北京",
            "workAddress": "北京市丰台区汉威国际广场四区 1 号楼 7 层",
            "salaryText": "25-50K",
            "companySize": "100-499人",
            "experience": "5-10年",
            "education": "本科",
            "description": "负责 RAG 应用研发与 Agent 平台建设",
        }
    )
    second = client.post("/v1/jobs/capture", json=payload)

    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "jobIds": ["job-123"]}
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "jobIds": []}

    listing = client.get("/v1/jobs")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    item = listing.json()["items"][0]
    assert item["salaryText"] == "25-50K"
    assert item["companySize"] == "100-499人"
    assert item["location"] == "北京"
    assert item["workAddress"] == "北京市丰台区汉威国际广场四区 1 号楼 7 层"
    assert item["experience"] == "5-10年"
    assert item["education"] == "本科"
    assert item["description"] == "负责 RAG 应用研发与 Agent 平台建设"
    snapshot_id = item["id"]

    deleted = client.delete(f"/v1/jobs/{snapshot_id}")
    assert deleted.status_code == 204
    assert client.get("/v1/jobs").json()["total"] == 0


def test_job_snapshots_support_server_side_pagination_and_search(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    for index in range(1, 6):
        response = client.post(
            "/v1/jobs",
            json={
                "title": f"AI Agent 工程师 {index}",
                "companyName": "分页测试公司" if index <= 3 else "其他公司",
                "description": f"负责第 {index} 个 RAG 项目",
            },
        )
        assert response.status_code == 201

    first_page = client.get("/v1/jobs?page=1&pageSize=2").json()
    assert first_page["total"] == 5
    assert first_page["page"] == 1
    assert first_page["pageSize"] == 2
    assert first_page["totalPages"] == 3
    assert [item["title"] for item in first_page["items"]] == [
        "AI Agent 工程师 5",
        "AI Agent 工程师 4",
    ]

    last_page = client.get("/v1/jobs?page=3&pageSize=2").json()
    assert last_page["page"] == 3
    assert [item["title"] for item in last_page["items"]] == ["AI Agent 工程师 1"]

    searched = client.get(
        "/v1/jobs",
        params={"page": 1, "pageSize": 2, "query": "分页测试公司"},
    ).json()
    assert searched["total"] == 3
    assert searched["totalPages"] == 2
    assert len(searched["items"]) == 2

    first_id = first_page["items"][0]["id"]
    tracked = client.put(
        f"/v1/jobs/{first_id}/tracking",
        json={
            "hasCommunicated": True,
            "hasInterview": True,
            "resumeVariant": "default",
        },
    )
    assert tracked.status_code == 200

    communicated = client.get(
        "/v1/jobs", params={"communicationResult": "communicated"}
    ).json()
    assert communicated["total"] == 1
    assert communicated["items"][0]["id"] == first_id

    not_communicated = client.get(
        "/v1/jobs", params={"communicationResult": "not_communicated"}
    ).json()
    assert not_communicated["total"] == 4

    interviewed = client.get(
        "/v1/jobs", params={"communicationResult": "interviewed"}
    ).json()
    assert interviewed["total"] == 1


def test_create_manual_job_snapshot(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "未来智能科技",
            "companySize": "500-999人",
            "location": "北京",
            "workAddress": "北京市海淀区中关村软件园",
            "salaryText": "25-40K·14薪",
            "experience": "3-5年",
            "education": "本科",
            "description": "负责基于 LangGraph 和 RAG 的 AI Agent 平台研发。",
            "skills": ["Python", "FastAPI", "LangGraph", "RAG"],
            "recruiterName": "李女士",
            "recruiterTitle": "招聘经理",
        },
    )

    assert response.status_code == 201
    result = response.json()
    assert result["source"] == "manual"
    assert result["companySize"] == "500-999人"
    assert result["workAddress"] == "北京市海淀区中关村软件园"
    assert result["platformJobId"].startswith("manual-")
    assert result["contentHash"]
    assert result["hasCommunicated"] is False
    assert result["hasInterview"] is False
    assert result["resumeVariant"] == "default"

    tracking = client.put(
        f"/v1/jobs/{result['id']}/tracking",
        json={
            "hasCommunicated": True,
            "hasInterview": True,
            "generatedGreeting": "您好，我有 RAG 与 Agent 项目经验。",
            "resumeVariant": "optimized",
            "generatedResumeId": 12,
            "resumeOptimization": "突出 LangGraph、RAG 和 FastAPI 项目成果。",
        },
    )
    assert tracking.status_code == 200
    tracked = tracking.json()
    assert tracked["hasCommunicated"] is True
    assert tracked["hasInterview"] is True
    assert tracked["generatedGreeting"].startswith("您好")
    assert tracked["generatedResumeId"] == 12
    assert tracked["resumeVariant"] == "optimized"
    assert client.get("/v1/jobs").json()["items"][0]["title"] == "AI Agent 工程师"


def test_job_snapshot_automatically_generates_and_stores_greeting(tmp_path) -> None:
    generator = FakeGreetingGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={"data": {"summary": "熟悉 RAG 开发", "defaultGreeting": "默认问候语"}},
    )
    client.post(
        "/v1/library/projects",
        json={"name": "知识库项目", "data": {"summary": "RAG 检索", "tags": "RAG"}},
    )

    created = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "description": "负责 Agent 与 RAG 平台研发",
            "skills": ["Python", "RAG"],
        },
    )

    assert created.status_code == 201
    stored = client.get("/v1/jobs").json()["items"][0]
    assert stored["generatedGreeting"].startswith("您好")
    assert generator.contexts[0]["defaultGreeting"] == "默认问候语"
    assert generator.contexts[0]["profile"]["summary"] == "熟悉 RAG 开发"
    assert generator.contexts[0]["localEvidence"]
    assert "defaultResume" not in generator.contexts[0]


def test_job_snapshot_falls_back_to_default_greeting_without_blocking(tmp_path) -> None:
    generator = FakeGreetingGenerator("模型超时")
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={"data": {"defaultGreeting": "您好，我对贵司岗位很感兴趣。"}},
    )

    created = client.post(
        "/v1/jobs",
        json={
            "title": "Python 工程师",
            "companyName": "示例科技",
            "description": "负责 Python 服务开发",
        },
    )

    assert created.status_code == 201
    stored = client.get("/v1/jobs").json()["items"][0]
    assert stored["generatedGreeting"] == "您好，我对贵司岗位很感兴趣。"


def test_listing_jobs_backfills_missing_greeting_from_older_automation_runs(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    greeting_generator = FakeGreetingGenerator()
    client = TestClient(
        create_app(
            database_path,
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=greeting_generator,
        )
    )
    created = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "历史快照公司",
            "description": "负责 RAG 与 Agent 应用开发",
        },
    ).json()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE job_postings SET generated_greeting = NULL WHERE id = ?",
            (created["id"],),
        )

    first = client.get("/v1/jobs").json()
    second = client.get("/v1/jobs").json()

    assert first["items"][0]["generatedGreeting"] is None
    assert second["items"][0]["generatedGreeting"].startswith("您好")
    assert greeting_generator.contexts


def test_preview_job_materials_combines_all_local_sources(tmp_path) -> None:
    generator = FakeMaterialPreviewGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            material_preview_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "defaultGreeting": "您好，我对贵司岗位很感兴趣。",
                "workExperience": "示例公司 · AI 工程师",
                "education": "示例大学 · 本科",
            }
        },
    )
    client.post(
        "/v1/library/projects",
        json={
            "name": "企业知识库",
            "data": {"summary": "负责 RAG 检索服务", "tags": "RAG,Python"},
        },
    )
    client.post(
        "/v1/library/resumes",
        json={"name": "默认简历", "data": {"rawText": "默认简历原文"}},
    )
    job = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "description": "负责 Agent 与 RAG 平台研发",
            "skills": ["Python", "RAG"],
        },
    ).json()

    response = client.post(f"/v1/jobs/{job['id']}/material-preview", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["greeting"].startswith("您好")
    assert result["resume"]["projects"] == ["企业知识库：负责 RAG 检索"]
    assert result["match"]["evidence"]
    assert generator.context["job"]["description"] == "负责 Agent 与 RAG 平台研发"
    assert generator.context["profile"]["defaultGreeting"].startswith("您好")
    assert generator.context["localEvidence"]
    assert generator.context["defaultResume"]["rawText"] == "默认简历原文"


def test_job_analysis_supports_local_and_ai_modes(tmp_path) -> None:
    generator = FakeJobAnalysisGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            job_analysis_generator=generator,
        )
    )
    client.post(
        "/v1/library/projects",
        json={
            "name": "企业知识库",
            "data": {"summary": "负责 RAG 检索服务", "tags": "RAG,Python"},
        },
    )
    job = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "description": "负责 Agent 与 RAG 平台研发",
            "skills": ["Python", "RAG"],
        },
    ).json()

    local_response = client.post(
        f"/v1/jobs/{job['id']}/analysis", json={"useAi": False}
    )
    assert local_response.status_code == 200
    local = local_response.json()
    assert local["mode"] == "local"
    assert local["match"]["evidence"]
    assert local["modelRecordId"] is None
    assert "岗位适合度" in local["summary"]

    ai_response = client.post(
        f"/v1/jobs/{job['id']}/analysis",
        json={"useAi": True, "modelRecordId": 11},
    )
    assert ai_response.status_code == 200
    ai = ai_response.json()
    assert ai["mode"] == "ai"
    assert ai["modelName"] == "职位分析测试模型"
    assert ai["interviewQuestions"] == ["如何评估 RAG 检索质量？"]
    assert generator.model_record_id == 11
    assert generator.context["job"]["id"] == job["id"]


def test_job_analysis_returns_not_found_for_unknown_snapshot(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )

    response = client.post("/v1/jobs/999/analysis", json={"useAi": False})

    assert response.status_code == 404


def test_delivery_api_upserts_by_platform_job_id(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "platform": "boss",
        "platformJobId": "boss-job-1",
        "title": "AI Agent 开发工程师",
        "companyName": "示例公司",
        "salaryText": "20-40K",
        "location": "北京",
        "recruiterName": "罗女士",
        "status": "delivered",
        "decision": "APPROVE",
        "reason": "匹配 AI Agent 与 RAG 经验",
        "greetingText": "您好，方便沟通吗？",
        "detail": "问候语已发送",
        "appliedAt": "2026-09-29T09:00:00Z",
        "metadata": {"source": "boss-zhipin-deliver"},
    }

    first = client.post("/v1/deliveries", json=payload)
    assert first.status_code == 201
    assert first.json()["status"] == "delivered"

    payload["status"] = "greeting_sent"
    payload["detail"] = "问候语已送达"
    second = client.post("/v1/deliveries", json=payload)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "greeting_sent"

    listing = client.get("/v1/deliveries")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["platformJobId"] == "boss-job-1"


def test_automation_config_uses_profile_and_library_rules(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "targetRoles": ["AI Agent 工程师"],
                "cities": ["北京"],
                "defaultGreeting": "您好，想和您沟通这个岗位。",
                "minimumSuitabilityScore": 60,
                "minimumCustomizationConfidence": 80,
            }
        },
    )
    client.post(
        "/v1/library/rules",
        json={
            "name": "屏蔽外包",
            "data": {"pattern": "外包, 驻场", "action": "block_delivery"},
        },
    )

    response = client.get("/v1/automation/config")

    assert response.status_code == 200
    result = response.json()
    assert result["searchKeywords"] == ["AI Agent 工程师"]
    assert result["targetCities"] == ["北京"]
    assert result["cityCode"] == "101010100"
    assert result["minimumSuitabilityScore"] == 60
    assert result["matchingRules"][0]["patterns"] == ["外包", "驻场"]


def test_automation_config_prefers_explicit_boss_city_code(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put(
        "/v1/profile",
        json={"data": {"cities": ["北京"], "bossCityCode": "custom-code"}},
    )

    result = client.get("/v1/automation/config").json()

    assert result["cityCode"] == "custom-code"


def test_automation_config_allows_explicit_zero_minimum_salary(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put("/v1/profile", json={"data": {"minimumSalaryK": 0}})

    result = client.get("/v1/automation/config").json()

    assert result["minimumSalaryK"] == 0


def test_analyze_and_plan_atomically_saves_matches_and_generates_greeting(tmp_path) -> None:
    greeting_generator = FakeGreetingGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=greeting_generator,
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "defaultGreeting": "您好，我对贵司岗位很感兴趣。",
                "minimumSuitabilityScore": 60,
                "minimumCustomizationConfidence": 1,
            }
        },
    )
    request = {
        "job": {
            "platform": "boss",
            "platformJobId": "atomic-plan-1",
            "url": "https://www.zhipin.com/job_detail/atomic-plan-1.html",
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "location": "北京",
            "salaryText": "25-40K",
            "description": "负责 RAG 与 Agent 应用开发",
            "skills": ["Python", "RAG"],
            "capturedAt": "2026-09-30T08:00:00Z",
            "source": "dom",
        }
    }

    response = client.post("/v1/jobs/analyze-and-plan", json=request)

    assert response.status_code == 200
    result = response.json()
    assert result["snapshot"]["platformJobId"] == "atomic-plan-1"
    assert result["match"]["suitabilityScore"] >= 60
    assert result["match"]["decision"]["shouldDeliver"] is True
    assert result["generatedGreeting"].startswith("您好")
    assert client.get("/v1/jobs").json()["total"] == 1


def test_analyze_and_plan_normalizes_private_use_salary_before_persisting(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=FakeGreetingGenerator(),
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "minimumSalaryK": 20,
                "minimumSuitabilityScore": 1,
                "minimumCustomizationConfidence": 1,
            }
        },
    )

    response = client.post(
        "/v1/jobs/analyze-and-plan",
        json={
            "job": {
                "platform": "boss",
                "platformJobId": "pua-salary-plan",
                "url": "https://www.zhipin.com/job_detail/pua-salary-plan.html",
                "title": "AI Agent 工程师",
                "companyName": "示例科技",
                "salaryText": "\ue033\ue036-\ue034\ue036K·\ue032\ue035薪",
                "description": "负责 RAG 与 Agent 应用开发",
                "skills": ["Python", "RAG"],
                "capturedAt": "2026-10-03T08:00:00Z",
                "source": "dom",
            }
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["snapshot"]["salaryText"] == "25-35K·14薪"
    assert result["match"]["decision"]["shouldDeliver"] is True
    assert client.get("/v1/jobs").json()["items"][0]["salaryText"] == "25-35K·14薪"


def test_analyze_and_plan_blocks_salary_but_still_generates_preview_greeting(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=FakeGreetingGenerator(),
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "minimumSalaryK": 20,
                "minimumSuitabilityScore": 1,
                "minimumCustomizationConfidence": 1,
            }
        },
    )

    response = client.post(
        "/v1/jobs/analyze-and-plan",
        json={
            "job": {
                "platform": "boss",
                "platformJobId": "low-salary-plan",
                "url": "https://www.zhipin.com/job_detail/low-salary-plan.html",
                "title": "AI Agent 工程师",
                "companyName": "示例科技",
                "salaryText": "15-30K",
                "description": "负责 RAG 与 Agent 应用开发",
                "skills": ["Python", "RAG"],
                "capturedAt": "2026-10-03T08:00:00Z",
                "source": "dom",
            }
        },
    )

    assert response.status_code == 200
    result = response.json()
    decision = result["match"]["decision"]
    assert decision["shouldDeliver"] is False
    assert decision["materialStrategy"] == "blocked"
    assert any("上限 15K 低于最低薪资 20K，无交集" in reason for reason in decision["reasons"])
    assert decision["ruleMatches"][-1]["ruleId"] == "builtin:minimum-salary"
    assert result["generatedGreeting"].startswith("您好")
    assert client.get("/v1/jobs").json()["items"][0]["generatedGreeting"].startswith("您好")


def test_analyze_and_plan_enforces_allowed_range_from_price_rule(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=FakeGreetingGenerator(),
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "minimumSalaryK": 20,
                "minimumSuitabilityScore": 1,
                "minimumCustomizationConfidence": 1,
            }
        },
    )
    created_rule = client.post(
        "/v1/library/rules",
        json={
            "name": "价格",
            "data": {
                "pattern": "18k-35k不在这个价格区间的禁止投递",
                "action": "block_delivery",
            },
        },
    ).json()

    response = client.post(
        "/v1/jobs/analyze-and-plan",
        json={
            "job": {
                "platform": "boss",
                "platformJobId": "outside-price-rule",
                "url": "https://www.zhipin.com/job_detail/outside-price-rule.html",
                "title": "AI Agent 工程师",
                "companyName": "示例科技",
                "salaryText": "\ue034\ue037-\ue035\ue031K·\ue032\ue035薪",
                "description": "负责 RAG 与 Agent 应用开发",
                "skills": ["Python", "RAG"],
                "capturedAt": "2026-10-03T08:00:00Z",
                "source": "dom",
            }
        },
    )

    assert response.status_code == 200
    decision = response.json()["match"]["decision"]
    assert decision["shouldDeliver"] is False
    assert any("36-40K 与规则允许的 18-35K 无交集" in item for item in decision["reasons"])
    assert decision["ruleMatches"][-1]["ruleId"] == f"library:{created_rule['id']}"


def test_analyze_and_plan_blocks_jobs_below_threshold_but_keeps_preview_greeting(tmp_path) -> None:
    class ZeroEmbedder(MaterialPreviewEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0, 0.0] for _text in texts]

    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=ZeroEmbedder()))
    client.put(
        "/v1/profile",
        json={"data": {"minimumSuitabilityScore": 60, "summary": "平面设计"}},
    )
    response = client.post(
        "/v1/jobs/analyze-and-plan",
        json={
            "job": {
                "platform": "boss",
                "platformJobId": "atomic-plan-low",
                "url": "https://www.zhipin.com/job_detail/atomic-plan-low.html",
                "title": "销售经理",
                "companyName": "示例销售公司",
                "description": "负责销售团队管理和业绩目标",
                "capturedAt": "2026-09-30T08:00:00Z",
                "source": "dom",
            }
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["match"]["decision"]["shouldDeliver"] is False
    assert result["match"]["decision"]["materialStrategy"] == "blocked"
    assert result["generatedGreeting"]


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
