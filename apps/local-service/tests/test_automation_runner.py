from typing import Any

from job_search_assistant.automation.runner import execute_run, run_loop


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
