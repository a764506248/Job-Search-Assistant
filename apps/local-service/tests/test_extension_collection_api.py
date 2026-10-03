from typing import Any

from fastapi.testclient import TestClient

from job_search_assistant.automation.browser_protocol import BrowserProtocolError
from job_search_assistant.main import create_app


class DeterministicEmbedder:
    model = "test/extension-collection"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.5, 0.25] for _text in texts]


class DeterministicGreetingGenerator:
    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        return {
            "modelRecordId": 1,
            "modelName": "test-greeting",
            "modelId": "test-greeting",
            "greeting": "您好，我有 Agent 与 RAG 项目经验，希望进一步沟通。",
        }


class DeterministicModelTester:
    def test(self, _config: dict[str, object]) -> dict[str, object]:
        return {"status": "ok", "latencyMs": 1}


def captured_job(
    job_id: str,
    company_name: str,
    *,
    title: str = "AI Agent 工程师",
    description: str = "负责 Python、RAG 与 Agent 应用开发",
) -> dict[str, object]:
    return {
        "platform": "boss",
        "platformJobId": job_id,
        "url": f"https://www.zhipin.com/job_detail/{job_id}.html",
        "title": title,
        "companyName": company_name,
        "location": "北京",
        "salaryText": "25-40K",
        "description": description,
        "skills": ["Python", "RAG", "Agent"],
        "capturedAt": "2026-10-03T08:00:00Z",
        "source": "dom",
    }


class FakeConnectedBrowserHub:
    def __init__(
        self,
        jobs: list[dict[str, object]] | None = None,
        version: str = "0.4.11-test",
        *,
        logged_in: bool = True,
    ) -> None:
        self.jobs = jobs or []
        self.version = version
        self.logged_in = logged_in
        self.calls: list[dict[str, Any]] = []

    def status(self) -> dict[str, object]:
        return {
            "connected": True,
            "paired": True,
            "protocolVersion": "1.0",
            "extensionVersion": self.version,
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
        if action == "session_status":
            return {
                "requestId": f"session-{run_id}",
                "status": "success",
                "evidence": {
                    "bossDomain": True,
                    "documentReady": True,
                    "loggedIn": self.logged_in,
                },
            }
        if action == "navigate_search":
            return {
                "requestId": f"navigate-{run_id}",
                "status": "success",
                "evidence": {"query": payload.get("query")},
            }
        if action == "collect_jobs":
            raw_excluded = payload.get("excludeJobIds", [])
            excluded = (
                {str(job_id) for job_id in raw_excluded}
                if isinstance(raw_excluded, list)
                else set()
            )
            limit = int(payload.get("limit", 10))
            available = [
                job
                for job in self.jobs
                if str(job.get("platformJobId", "")) not in excluded
            ]
            batch = available[:limit]
            return {
                "requestId": f"collect-{run_id}",
                "status": "success",
                "evidence": {
                    "jobs": batch,
                    "collectedCount": len(batch),
                    "skipped": [],
                    "exhausted": len(available) <= limit,
                },
            }
        raise AssertionError(f"unexpected browser action during collection: {action}")


class TimeoutAfterFirstBatchHub(FakeConnectedBrowserHub):
    def __init__(self, jobs: list[dict[str, object]]) -> None:
        super().__init__(jobs)
        self.collect_calls = 0

    async def dispatch(
        self,
        *,
        run_id: int,
        action: str,
        payload: dict[str, object],
        deadline_ms: int,
    ) -> dict[str, object]:
        if action != "collect_jobs":
            return await super().dispatch(
                run_id=run_id,
                action=action,
                payload=payload,
                deadline_ms=deadline_ms,
            )
        self.collect_calls += 1
        if self.collect_calls == 1:
            self.calls.append(
                {
                    "runId": run_id,
                    "action": action,
                    "payload": payload,
                    "deadlineMs": deadline_ms,
                }
            )
            return {
                "requestId": f"collect-{run_id}-1",
                "status": "success",
                "evidence": {
                    "jobs": self.jobs[:1],
                    "collectedCount": 1,
                    "skipped": [],
                    "exhausted": False,
                },
            }
        self.calls.append(
            {
                "runId": run_id,
                "action": action,
                "payload": payload,
                "deadlineMs": deadline_ms,
            }
        )
        raise BrowserProtocolError("browser action timed out: collect_jobs")


class AlwaysTimeoutHub(FakeConnectedBrowserHub):
    async def dispatch(
        self,
        *,
        run_id: int,
        action: str,
        payload: dict[str, object],
        deadline_ms: int,
    ) -> dict[str, object]:
        if action != "collect_jobs":
            return await super().dispatch(
                run_id=run_id,
                action=action,
                payload=payload,
                deadline_ms=deadline_ms,
            )
        self.calls.append(
            {
                "runId": run_id,
                "action": action,
                "payload": payload,
                "deadlineMs": deadline_ms,
            }
        )
        raise BrowserProtocolError("browser action timed out: collect_jobs")


def collection_client(tmp_path, hub: FakeConnectedBrowserHub) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=DeterministicEmbedder(),
            greeting_generator=DeterministicGreetingGenerator(),
            model_tester=DeterministicModelTester(),
            browser_hub=hub,
        )
    )


def create_pending_run(
    client: TestClient,
    target_count: int = 2,
    candidate_limit: int | None = None,
    extra_config: dict[str, object] | None = None,
) -> dict[str, object]:
    config = {
        "searchKeywords": ["AI Agent"],
        "cityCode": "101010100",
        "minimumSuitabilityScore": 0,
        "minimumCustomizationConfidence": 0,
    }
    if candidate_limit is not None:
        config["candidateLimit"] = candidate_limit
    config.update(extra_config or {})
    response = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": target_count,
            "config": config,
        },
    )
    assert response.status_code == 201
    return response.json()


def configure_ready_delivery_environment(client: TestClient) -> None:
    profile = client.put(
        "/v1/profile",
        json={
            "data": {
                "targetRoles": ["AI Agent 工程师"],
                "cities": ["北京"],
                "bossCityCode": "101010100",
                "defaultGreeting": "您好，我有 Agent 与 RAG 项目经验，希望进一步沟通。",
            }
        },
    )
    resume = client.post(
        "/v1/library/resumes",
        json={"name": "默认简历", "data": {"rawText": "Python、RAG 与 Agent 项目经验"}},
    )
    project = client.post(
        "/v1/library/projects",
        json={
            "name": "Agent 项目",
            "data": {"summary": "负责 Python、RAG 与 Agent 应用开发", "tags": "Python,RAG,Agent"},
        },
    )
    model = client.post(
        "/v1/library/models",
        json={
            "name": "测试模型",
            "data": {
                "modelId": "test-model",
                "apiKey": "test-secret",
                "baseUrl": "https://model.invalid/v1",
            },
        },
    )
    assert profile.status_code == 200
    assert resume.status_code == 201
    assert project.status_code == 201
    assert model.status_code == 201
    assert client.post(f"/v1/library/models/{model.json()['id']}/test").status_code == 200
    assert client.post(
        "/v1/setup/browser/probe",
        json={"projectExtensionReady": True, "bossLoggedIn": True, "source": "manual"},
    ).status_code == 200
    assert client.post(
        "/v1/automation/runner/heartbeat", json={"runnerId": "test-runner"}
    ).status_code == 200
    assert client.get("/v1/setup/status").json()["overall"] == "ready"


def test_new_run_automatically_collects_and_never_reuses_historical_sqlite_jobs(
    tmp_path,
) -> None:
    hub = FakeConnectedBrowserHub([captured_job("fresh-job", "新公司")])
    client = collection_client(tmp_path, hub)
    historical = captured_job("historical-job", "历史公司")
    historical["generatedGreeting"] = "历史问候语"

    saved = client.post("/v1/jobs/capture", json={"jobs": [historical]})
    created = create_pending_run(
        client,
        extra_config={
            "collectionIntervalMs": 3500,
            "collectionFilters": {
                "jobType": "1901",
                "salary": "406",
                "experience": "105",
                "degree": "206",
                "industry": "100021",
                "scale": "304",
            },
        },
    )

    assert saved.status_code == 200
    assert created["status"] == "draft"
    assert created["configSnapshot"]["plannedJobs"] == []
    assert created["configSnapshot"]["collection"]["status"] == "pending"
    assert created["configSnapshot"]["collection"]["phase"] == "queued"

    persisted = client.get(f"/v1/automation/runs/{created['id']}").json()

    assert persisted["status"] == "draft"
    assert persisted["configSnapshot"]["collection"]["status"] == "ready"
    assert persisted["configSnapshot"]["collection"]["phase"] == "awaiting_confirmation"
    assert [job["jobId"] for job in persisted["configSnapshot"]["plannedJobs"]] == [
        "fresh-job"
    ]
    assert "historical-job" not in {
        job["jobId"] for job in persisted["configSnapshot"]["plannedJobs"]
    }
    assert client.get("/v1/jobs").json()["total"] == 2
    assert hub.calls[1]["payload"] == {
        "query": "AI Agent",
        "cityCode": "101010100",
        "filters": {
            "jobType": "1901",
            "salary": "406",
            "experience": "105",
            "degree": "206",
            "industry": "100021",
            "scale": "304",
        },
    }
    assert hub.calls[2]["payload"]["excludeJobIds"] == ["historical-job"]
    assert hub.calls[2]["payload"]["itemIntervalMs"] == 3500


def test_automatic_pipeline_deduplicates_analyzes_and_never_sends(tmp_path) -> None:
    first = captured_job("fresh-job-1", "甲科技")
    duplicate = {**first, "description": "同一职位的重复卡片"}
    second = captured_job("fresh-job-2", "乙智能", title="RAG 平台工程师")
    historical = captured_job("historical-job", "历史公司")
    historical["generatedGreeting"] = "历史问候语"
    hub = FakeConnectedBrowserHub([historical, first, duplicate, second])
    client = collection_client(tmp_path, hub)
    client.post("/v1/jobs/capture", json={"jobs": [historical]})
    created = create_pending_run(client)

    run = client.get(f"/v1/automation/runs/{created['id']}").json()
    assert run["status"] == "draft"
    assert run["configSnapshot"]["collection"]["status"] == "ready"
    assert run["configSnapshot"]["collection"]["phase"] == "awaiting_confirmation"
    assert run["configSnapshot"]["collection"]["collectedCount"] == 2
    assert run["configSnapshot"]["collection"]["existingExcludedCount"] == 1
    assert run["configSnapshot"]["collection"]["analyzedCount"] == 2
    assert run["configSnapshot"]["collection"]["approvedCount"] == 2
    planned_jobs = run["configSnapshot"]["plannedJobs"]
    assert [job["jobId"] for job in planned_jobs] == ["fresh-job-1", "fresh-job-2"]
    assert [job["companyName"] for job in planned_jobs] == ["甲科技", "乙智能"]
    assert "historical-job" not in {job["jobId"] for job in planned_jobs}

    actions = [call["action"] for call in hub.calls]
    assert actions == ["session_status", "navigate_search", "collect_jobs"]
    assert not ({"send_greeting", "send_resume"} & set(actions))
    assert hub.calls[1]["payload"] == {
        "query": "AI Agent",
        "cityCode": "101010100",
        "filters": {},
    }
    assert hub.calls[2]["payload"]["excludeJobIds"] == ["historical-job"]
    assert hub.calls[2]["payload"]["itemIntervalMs"] == 2000

    events = client.get(f"/v1/automation/runs/{created['id']}/events").json()["items"]
    event_types = [event["eventType"] for event in events]
    assert event_types[0:3] == ["run-created", "collection-queued", "collection-started"]
    assert "analysis-started" in event_types
    assert event_types[-2:] == ["collection-finished", "collection-stage-changed"]
    phases = [
        event["payload"].get("phase")
        for event in events
        if event["eventType"] == "collection-stage-changed"
    ]
    assert phases == ["searching", "collecting", "analyzing", "awaiting_confirmation"]

    calls_before_idempotent_retry = len(hub.calls)
    retry = client.post(f"/v1/automation/runs/{created['id']}/collect")
    assert retry.status_code == 202
    assert retry.json()["configSnapshot"]["collection"]["status"] == "ready"
    assert len(hub.calls) == calls_before_idempotent_retry


def test_all_rule_rejected_jobs_are_a_reviewed_no_matches_outcome(tmp_path) -> None:
    rejected = captured_job("salary-rejected-job", "薪资规则测试公司")
    rejected["salaryText"] = "10-15K"
    hub = FakeConnectedBrowserHub([rejected])
    client = collection_client(tmp_path, hub)

    created = create_pending_run(client, target_count=1)
    run_id = created["id"]
    run = client.get(f"/v1/automation/runs/{run_id}").json()
    collection = run["configSnapshot"]["collection"]

    assert run["status"] == "draft"
    assert run["configSnapshot"]["plannedJobs"] == []
    assert collection["status"] == "no_matches"
    assert collection["phase"] == "analysis_completed"
    assert collection["error"] is None
    assert collection["attemptId"] == 1
    assert collection["collectedCount"] == 1
    assert collection["analyzedCount"] == 1
    assert collection["approvedCount"] == 0
    assert collection["rejectedCount"] == 1
    assert collection["ruleRejectedCount"] == 1
    assert collection["duplicateCount"] == 0
    assert collection["materialErrorCount"] == 0
    assert collection["analysisErrorCount"] == 0

    reviewed = collection["reviewedJobs"]
    assert len(reviewed) == 1
    assert reviewed[0]["snapshotId"]
    assert reviewed[0]["jobId"] == "salary-rejected-job"
    assert reviewed[0]["companyName"] == "薪资规则测试公司"
    assert reviewed[0]["salaryText"] == "10-15K"
    assert reviewed[0]["outcome"] == "rule_rejected"
    assert reviewed[0]["suitabilityScore"] is not None
    assert any("低于最低薪资 20K" in reason for reason in reviewed[0]["reasons"])
    assert any(
        match["ruleId"] == "builtin:minimum-salary"
        for match in reviewed[0]["ruleMatches"]
    )

    events = client.get(f"/v1/automation/runs/{run_id}/events").json()["items"]
    terminal = events[-1]
    assert terminal["eventType"] == "analysis-finished"
    assert terminal["level"] == "info"
    assert terminal["payload"]["attemptId"] == 1
    assert terminal["payload"]["outcome"] == "no_matches"
    assert terminal["payload"]["reviewedJobs"][0]["outcome"] == "rule_rejected"

    retried = client.post(f"/v1/automation/runs/{run_id}/collect")
    assert retried.status_code == 202
    final = client.get(f"/v1/automation/runs/{run_id}").json()
    assert final["configSnapshot"]["collection"]["status"] == "no_matches"
    assert final["configSnapshot"]["collection"]["attemptId"] == 2
    terminal_events = [
        event
        for event in client.get(
            f"/v1/automation/runs/{run_id}/events"
        ).json()["items"]
        if event["eventType"] == "analysis-finished"
    ]
    assert [event["payload"]["attemptId"] for event in terminal_events] == [1, 2]


def test_collection_continues_past_old_three_times_target_until_match(tmp_path) -> None:
    rejected_jobs = []
    for index in range(12):
        job = captured_job(f"rejected-{index}", f"不匹配公司{index}")
        job["salaryText"] = "10-15K"
        rejected_jobs.append(job)
    approved = captured_job("eventual-match", "最终匹配公司")
    hub = FakeConnectedBrowserHub([*rejected_jobs, approved])
    client = collection_client(tmp_path, hub)

    created = create_pending_run(client, target_count=1, candidate_limit=20)
    run = client.get(f"/v1/automation/runs/{created['id']}").json()
    collection = run["configSnapshot"]["collection"]
    collect_calls = [call for call in hub.calls if call["action"] == "collect_jobs"]

    assert collection["candidateLimit"] == 20
    assert collection["collectedCount"] == 13
    assert collection["analyzedCount"] == 13
    assert collection["approvedCount"] == 1
    assert collection["rejectedCount"] == 12
    assert [job["jobId"] for job in run["configSnapshot"]["plannedJobs"]] == [
        "eventual-match"
    ]
    assert run["configSnapshot"]["plannedJobs"][0]["greeting"]
    assert len(collect_calls) == 2


def test_pipeline_stops_at_confirmation_then_only_selected_jobs_can_start(tmp_path) -> None:
    hub = FakeConnectedBrowserHub(
        [
            captured_job("fresh-job-1", "甲科技"),
            captured_job("fresh-job-2", "乙智能", title="RAG 平台工程师"),
        ]
    )
    client = collection_client(tmp_path, hub)
    configure_ready_delivery_environment(client)
    created = create_pending_run(client, target_count=2)
    run_id = created["id"]

    ready = client.get(f"/v1/automation/runs/{run_id}").json()
    assert ready["status"] == "draft"
    assert ready["configSnapshot"]["collection"]["phase"] == "awaiting_confirmation"
    assert client.post(
        "/v1/automation/runner/claim", json={"runnerId": "test-runner"}
    ).json()["run"] is None

    without_confirmation = client.post(f"/v1/automation/runs/{run_id}/start")
    assert without_confirmation.status_code == 422
    assert without_confirmation.json()["detail"] == "请先确认至少一个待投企业"
    assert client.get(f"/v1/automation/runs/{run_id}").json()["status"] == "draft"

    confirmed = client.post(
        f"/v1/automation/runs/{run_id}/start",
        json={"selectedJobIds": ["fresh-job-2"]},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "running"
    assert confirmed.json()["targetCount"] == 1
    assert [job["jobId"] for job in confirmed.json()["configSnapshot"]["plannedJobs"]] == [
        "fresh-job-2"
    ]
    claimed = client.post(
        "/v1/automation/runner/claim", json={"runnerId": "test-runner"}
    ).json()["run"]
    assert claimed["id"] == run_id
    assert [call["action"] for call in hub.calls] == [
        "session_status",
        "navigate_search",
        "collect_jobs",
    ]


def test_collect_recovers_an_interrupted_collecting_state(tmp_path) -> None:
    hub = FakeConnectedBrowserHub([captured_job("recovered-job", "恢复公司")])
    client = collection_client(tmp_path, hub)
    created = client.post(
        "/v1/automation/runs",
        json={
            "targetCount": 1,
            "config": {
                "searchKeywords": ["AI Agent"],
                "cityCode": "101010100",
                "minimumSuitabilityScore": 0,
                "minimumCustomizationConfidence": 0,
                "plannedJobs": [],
                "collection": {
                    "status": "collecting",
                    "phase": "collecting",
                    "source": "extension",
                },
            },
        },
    ).json()
    assert client.get(f"/v1/automation/runs/{created['id']}").json()["configSnapshot"][
        "collection"
    ]["status"] == "collecting"

    queued = client.post(f"/v1/automation/runs/{created['id']}/collect")
    recovered = client.get(f"/v1/automation/runs/{created['id']}").json()

    assert queued.status_code == 202
    assert queued.json()["configSnapshot"]["collection"]["status"] == "pending"
    assert queued.json()["configSnapshot"]["collection"]["phase"] == "queued"
    assert recovered["configSnapshot"]["collection"]["status"] == "ready"
    assert recovered["configSnapshot"]["collection"]["phase"] == "awaiting_confirmation"
    assert [call["action"] for call in hub.calls] == [
        "session_status",
        "navigate_search",
        "collect_jobs",
    ]


def test_connected_unified_extension_makes_legacy_skill_optional(tmp_path) -> None:
    hub = FakeConnectedBrowserHub()
    client = collection_client(tmp_path, hub)

    checks = {
        item["key"]: item for item in client.get("/v1/setup/status").json()["checks"]
    }

    assert checks["kimi-webbridge"]["label"] == "统一浏览器扩展"
    assert checks["kimi-webbridge"]["status"] == "ready"
    assert checks["kimi-webbridge"]["blocking"] is False
    assert checks["boss-login"]["status"] == "pending"
    assert checks["boss-login"]["blocking"] is False
    assert "自动确认" in checks["boss-login"]["message"]
    assert checks["skill-version"]["status"] == "ready"
    assert checks["skill-version"]["blocking"] is False
    assert "不需要安装 Skill" in checks["skill-version"]["message"]


def test_collection_uses_short_observable_batches_and_exclusions(tmp_path) -> None:
    jobs = [captured_job(f"batch-job-{index}", f"公司{index}") for index in range(12)]
    hub = FakeConnectedBrowserHub(jobs)
    client = collection_client(tmp_path, hub)
    created = create_pending_run(client, target_count=4)

    run = client.get(f"/v1/automation/runs/{created['id']}").json()
    collection = run["configSnapshot"]["collection"]
    collect_calls = [call for call in hub.calls if call["action"] == "collect_jobs"]

    assert collection["status"] == "ready"
    assert collection["collectedCount"] == 12
    assert len(collect_calls) == 2
    assert collect_calls[0]["payload"] == {
        "limit": 10,
        "excludeJobIds": [],
        "itemIntervalMs": 2000,
    }
    assert collect_calls[0]["deadlineMs"] == 50_000
    assert collect_calls[1]["payload"]["limit"] == 10
    assert collect_calls[1]["payload"]["excludeJobIds"] == [
        f"batch-job-{index}" for index in range(10)
    ]
    assert collect_calls[1]["deadlineMs"] == 50_000

    events = client.get(f"/v1/automation/runs/{created['id']}/events").json()["items"]
    batch_events = [
        event for event in events if event["eventType"] == "collection-batch-finished"
    ]
    assert [event["payload"]["collectedCount"] for event in batch_events] == [10, 12]
    assert [event["payload"]["newCount"] for event in batch_events] == [10, 2]
    checks = {
        item["key"]: item for item in client.get("/v1/setup/status").json()["checks"]
    }
    assert checks["boss-login"]["status"] == "ready"
    assert checks["boss-login"]["blocking"] is False


def test_collection_timeout_keeps_and_analyzes_completed_batches(tmp_path) -> None:
    hub = TimeoutAfterFirstBatchHub([captured_job("retained-job", "保留公司")])
    client = collection_client(tmp_path, hub)
    created = create_pending_run(client, target_count=1)

    run = client.get(f"/v1/automation/runs/{created['id']}").json()
    collection = run["configSnapshot"]["collection"]
    collect_calls = [call for call in hub.calls if call["action"] == "collect_jobs"]

    assert collection["status"] == "ready"
    assert collection["phase"] == "awaiting_confirmation"
    assert collection["collectedCount"] == 1
    assert collection["partial"] is True
    assert any(
        "扩展采集单批职位超时，请适当降低岗位采集间隔" in error
        for error in collection["browserErrors"]
    )
    assert [job["jobId"] for job in run["configSnapshot"]["plannedJobs"]] == [
        "retained-job"
    ]
    assert len(collect_calls) == 2
    assert collect_calls[1]["payload"]["excludeJobIds"] == ["retained-job"]
    assert client.get("/v1/jobs").json()["total"] == 1

    events = client.get(f"/v1/automation/runs/{created['id']}/events").json()["items"]
    timeout_event = next(
        event for event in events if event["eventType"] == "collection-batch-failed"
    )
    assert timeout_event["payload"]["retainedCount"] == 1
    assert timeout_event["payload"]["error"] == "扩展采集单批职位超时，请适当降低岗位采集间隔"


def test_collection_timeout_without_results_fails_with_chinese_error(tmp_path) -> None:
    hub = AlwaysTimeoutHub()
    client = collection_client(tmp_path, hub)
    created = create_pending_run(client, target_count=1)

    run = client.get(f"/v1/automation/runs/{created['id']}").json()

    assert run["configSnapshot"]["collection"]["status"] == "failed"
    assert run["configSnapshot"]["collection"]["error"] == (
        "AI Agent：扩展采集单批职位超时，请适当降低岗位采集间隔"
    )
    assert run["configSnapshot"]["collection"]["collectedCount"] == 0
    assert run["configSnapshot"]["collection"]["attemptId"] == 1
    events = client.get(
        f"/v1/automation/runs/{created['id']}/events"
    ).json()["items"]
    terminal = events[-1]
    assert terminal["eventType"] == "collection-failed"
    assert terminal["level"] == "error"
    assert terminal["payload"]["attemptId"] == 1


def test_collection_stops_before_navigation_when_boss_is_logged_out(tmp_path) -> None:
    hub = FakeConnectedBrowserHub(
        [captured_job("fresh-job-1", "甲科技")],
        logged_in=False,
    )
    client = collection_client(tmp_path, hub)
    created = create_pending_run(client, target_count=1)

    run = client.get(f"/v1/automation/runs/{created['id']}").json()

    assert run["configSnapshot"]["collection"]["status"] == "failed"
    assert "BOSS 登录状态无效" in run["configSnapshot"]["collection"]["error"]
    assert [call["action"] for call in hub.calls] == ["session_status"]
    checks = {
        item["key"]: item for item in client.get("/v1/setup/status").json()["checks"]
    }
    assert checks["boss-login"]["status"] == "blocked"
    assert checks["boss-login"]["blocking"] is True


def test_outdated_extension_is_blocked_before_collection_dispatch(tmp_path) -> None:
    hub = FakeConnectedBrowserHub(
        [captured_job("fresh-job-1", "甲科技")],
        version="0.4.5",
    )
    client = collection_client(tmp_path, hub)
    created = create_pending_run(client, target_count=1)

    failed = client.get(f"/v1/automation/runs/{created['id']}").json()
    response = client.post(f"/v1/automation/runs/{created['id']}/collect")
    retried = client.get(f"/v1/automation/runs/{created['id']}").json()

    assert failed["configSnapshot"]["collection"]["status"] == "failed"
    assert failed["configSnapshot"]["collection"]["phase"] == "failed"
    assert "v0.4.11" in failed["configSnapshot"]["collection"]["error"]
    assert response.status_code == 202
    assert retried["configSnapshot"]["collection"]["status"] == "failed"
    assert hub.calls == []
    checks = {
        item["key"]: item for item in client.get("/v1/setup/status").json()["checks"]
    }
    assert checks["kimi-webbridge"]["status"] == "blocked"
    assert "v0.4.5" in checks["kimi-webbridge"]["message"]
    assert "v0.4.11" in checks["kimi-webbridge"]["message"]
