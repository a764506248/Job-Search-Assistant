from typing import Any

from job_search_assistant.automation.runner import execute_run, run_loop, wait_until_runnable


class FakeApi:
    def __init__(self, run: dict[str, Any] | None = None) -> None:
        self.run = run
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, body))
        if path == "/v1/automation/runner/claim":
            claimed, self.run = self.run, None
            return {"run": claimed}
        return {}

    def get(self, path: str) -> dict[str, Any]:
        self.calls.append((path, {}))
        return {"status": "running"}


def test_runner_registers_heartbeat_before_claiming() -> None:
    api = FakeApi()

    run_loop(api, "compose-runner", once=True)

    assert [path for path, _ in api.calls] == [
        "/v1/automation/runner/heartbeat",
        "/v1/automation/runner/claim",
    ]


def test_runner_blocks_empty_plan_without_browser_action() -> None:
    api = FakeApi()
    run = {"id": 7, "configSnapshot": {"plannedJobs": []}}

    execute_run(api, run, "compose-runner", dry_run=False)

    paths = [path for path, _ in api.calls]
    assert paths == [
        "/v1/automation/runs/7/heartbeat",
        "/v1/automation/runs/7/runner-finish",
    ]
    assert api.calls[-1][1]["status"] == "blocked"
    assert "未执行浏览器操作" in api.calls[-1][1]["reason"]


class ExecutingApi(FakeApi):
    def __init__(self, action_status: str = "success") -> None:
        super().__init__()
        self.action_status = action_status

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, body))
        if path.endswith("/browser-action"):
            return {
                "result": {
                    "status": self.action_status,
                    "error": "身份不匹配" if self.action_status != "success" else None,
                }
            }
        return {}


def planned_run() -> dict[str, Any]:
    return {
        "id": 8,
        "configSnapshot": {
            "plannedJobs": [{
                "jobId": "job-1",
                "url": "https://www.zhipin.com/job_detail/job-1.html",
                "title": "AI 工程师",
                "companyName": "示例公司",
                "greeting": "您好",
            }]
        },
    }


def test_runner_marks_all_failed_plan_as_failed() -> None:
    api = ExecutingApi(action_status="blocked")

    execute_run(api, planned_run(), "compose-runner", dry_run=False)

    finish = next(body for path, body in reversed(api.calls) if path.endswith("/runner-finish"))
    assert finish["status"] == "failed"
    assert finish["reason"] == "全部计划岗位处理失败"


def test_runner_sends_job_id_for_browser_identity_checks() -> None:
    api = ExecutingApi(action_status="success")

    execute_run(api, planned_run(), "compose-runner", dry_run=False)

    identity_calls = [
        body
        for path, body in api.calls
        if path.endswith("/browser-action")
        and body["action"] in {"open_chat", "validate_identity"}
    ]
    assert identity_calls
    assert all(call["payload"]["expectedJobId"] == "job-1" for call in identity_calls)


def test_runner_stops_before_next_browser_action_when_cancelled() -> None:
    class CancelledApi(ExecutingApi):
        def get(self, path: str) -> dict[str, Any]:
            self.calls.append((path, {}))
            return {"status": "cancelled"}

    api = CancelledApi()

    execute_run(api, planned_run(), "compose-runner", dry_run=False)

    assert not any(path.endswith("/browser-action") for path, _ in api.calls)
    assert not any(path.endswith("/runner-finish") for path, _ in api.calls)


def test_runner_waits_while_paused_and_resumes(monkeypatch) -> None:
    class PausedApi(FakeApi):
        statuses = iter(["paused", "running"])

        def get(self, path: str) -> dict[str, Any]:
            self.calls.append((path, {}))
            return {"status": next(self.statuses)}

    api = PausedApi()
    monkeypatch.setattr("job_search_assistant.automation.runner.time.sleep", lambda _: None)

    wait_until_runnable(api, 9, "compose-runner")

    assert ("/v1/automation/runner/heartbeat", {"runnerId": "compose-runner"}) in api.calls
    assert ("/v1/automation/runs/9/heartbeat", {"runnerId": "compose-runner"}) in api.calls
