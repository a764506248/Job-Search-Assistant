"""Automation worker packaged with the local-service Docker image."""

import argparse
import json
import platform
import time
import urllib.error
import urllib.request
from typing import Any


class LocalApi:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=130) as response:
            return json.load(response)

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


class RunHalted(Exception):
    """Raised when a task was stopped while the runner was executing it."""


def wait_until_runnable(
    api: LocalApi,
    run_id: int,
    runner_id: str,
    *,
    poll_seconds: float = 1.0,
) -> None:
    """Cooperatively honor pause/resume/stop before every browser side effect."""
    while True:
        run = api.get(f"/v1/automation/runs/{run_id}")
        status = str(run.get("status", ""))
        if status == "running":
            return
        if status != "paused":
            raise RunHalted(status or "unknown")
        api.post("/v1/automation/runner/heartbeat", {"runnerId": runner_id})
        api.post(f"/v1/automation/runs/{run_id}/heartbeat", {"runnerId": runner_id})
        time.sleep(max(poll_seconds, 0.2))


def browser_action(
    api: LocalApi,
    run_id: int,
    runner_id: str,
    *,
    job_id: str,
    action: str,
    payload: dict[str, Any],
    deadline_ms: int = 20_000,
) -> dict[str, Any]:
    wait_until_runnable(api, run_id, runner_id)
    api.post("/v1/automation/runner/heartbeat", {"runnerId": runner_id})
    return api.post(
        f"/v1/automation/runs/{run_id}/browser-action",
        {
            "runnerId": runner_id,
            "jobId": job_id,
            "action": action,
            "payload": payload,
            "deadlineMs": deadline_ms,
        },
    )


def record_progress(
    api: LocalApi,
    run_id: int,
    runner_id: str,
    job_id: str,
    outcome: str,
    reason: str,
) -> None:
    api.post(
        f"/v1/automation/runs/{run_id}/progress",
        {
            "runnerId": runner_id,
            "jobId": job_id,
            "outcome": outcome,
            "reason": reason,
        },
    )


def finish_run(
    api: LocalApi,
    run_id: int,
    runner_id: str,
    status: str,
    reason: str,
) -> None:
    api.post(
        f"/v1/automation/runs/{run_id}/runner-finish",
        {"runnerId": runner_id, "status": status, "reason": reason},
    )


def execute_run(api: LocalApi, run: dict[str, Any], runner_id: str, dry_run: bool) -> None:
    run_id = int(run["id"])
    config = run.get("configSnapshot", {})
    api.post(f"/v1/automation/runs/{run_id}/heartbeat", {"runnerId": runner_id})
    if dry_run:
        finish_run(api, run_id, runner_id, "completed", "runner-dry-run")
        return

    planned_jobs = config.get("plannedJobs", [])
    if not isinstance(planned_jobs, list) or not planned_jobs:
        finish_run(
            api,
            run_id,
            runner_id,
            "blocked",
            "没有可执行的岗位计划；未执行浏览器操作",
        )
        return

    success_count = 0
    failure_count = 0
    try:
        for job in planned_jobs:
            wait_until_runnable(api, run_id, runner_id)
            if not isinstance(job, dict):
                failure_count += 1
                record_progress(api, run_id, runner_id, "unknown", "failure", "计划格式错误")
                continue
            job_id = str(job.get("jobId", ""))
            expected_title = str(job.get("title", ""))
            expected_company = str(job.get("companyName", ""))
            greeting = str(job.get("greeting", ""))
            job_url = str(job.get("url", ""))
            if not all((job_id, job_url, expected_title, expected_company, greeting)):
                failure_count += 1
                record_progress(
                    api,
                    run_id,
                    runner_id,
                    job_id or "unknown",
                    "failure",
                    "计划字段不完整",
                )
                continue

            opened = browser_action(
                api,
                run_id,
                runner_id,
                job_id=job_id,
                action="open_job",
                payload={"url": job_url},
            )
            if opened.get("result", {}).get("status") != "success":
                failure_count += 1
                reason = opened.get("result", {}).get("error") or "打开岗位失败"
                record_progress(api, run_id, runner_id, job_id, "failure", str(reason))
                continue

            chat = browser_action(
                api,
                run_id,
                runner_id,
                job_id=job_id,
                action="open_chat",
                payload={
                    "expectedJobId": job_id,
                    "expectedTitle": expected_title,
                    "expectedCompany": expected_company,
                },
            )
            if chat.get("result", {}).get("status") != "success":
                failure_count += 1
                reason = chat.get("result", {}).get("error") or "打开沟通失败"
                record_progress(api, run_id, runner_id, job_id, "failure", str(reason))
                continue

            identity = browser_action(
                api,
                run_id,
                runner_id,
                job_id=job_id,
                action="validate_identity",
                payload={
                    "expectedJobId": job_id,
                    "expectedTitle": expected_title,
                    "expectedCompany": expected_company,
                    "requireChat": True,
                },
            )
            if identity.get("result", {}).get("status") != "success":
                failure_count += 1
                reason = identity.get("result", {}).get("error") or "岗位身份校验失败"
                record_progress(api, run_id, runner_id, job_id, "failure", str(reason))
                continue

            sent = browser_action(
                api,
                run_id,
                runner_id,
                job_id=job_id,
                action="send_greeting",
                payload={
                    "expectedTitle": expected_title,
                    "expectedCompany": expected_company,
                    "text": greeting,
                },
                deadline_ms=60_000,
            )
            greeting_status = sent.get("result", {}).get("status")
            if greeting_status != "success":
                failure_count += 1
                reason = sent.get("result", {}).get("error") or (
                    f"问候语发送失败：{greeting_status or 'unknown'}"
                )
                record_progress(api, run_id, runner_id, job_id, "failure", str(reason))
                finish_run(api, run_id, runner_id, "blocked", str(reason))
                return

            if config.get("sendResumeImage"):
                resume = browser_action(
                    api,
                    run_id,
                    runner_id,
                    job_id=job_id,
                    action="send_resume",
                    payload={
                        "expectedTitle": expected_title,
                        "expectedCompany": expected_company,
                    },
                    deadline_ms=60_000,
                )
                resume_status = resume.get("result", {}).get("status")
                if resume_status != "success":
                    failure_count += 1
                    reason = resume.get("result", {}).get("error") or (
                        f"简历发送失败：{resume_status or 'unknown'}"
                    )
                    record_progress(api, run_id, runner_id, job_id, "failure", str(reason))
                    finish_run(api, run_id, runner_id, "blocked", str(reason))
                    return
            success_count += 1
            record_progress(api, run_id, runner_id, job_id, "success", "投递已确认")
    except RunHalted:
        return

    try:
        wait_until_runnable(api, run_id, runner_id)
    except RunHalted:
        return
    if failure_count and not success_count:
        finish_run(api, run_id, runner_id, "failed", "全部计划岗位处理失败")
    elif failure_count:
        finish_run(api, run_id, runner_id, "completed", f"处理完成，{failure_count} 个岗位失败")
    else:
        finish_run(api, run_id, runner_id, "completed", "全部计划岗位处理完成")


def run_loop(
    api: LocalApi,
    runner_id: str,
    *,
    dry_run: bool = False,
    once: bool = False,
    poll_seconds: float = 2.0,
) -> None:
    while True:
        try:
            api.post("/v1/automation/runner/heartbeat", {"runnerId": runner_id})
            claimed = api.post("/v1/automation/runner/claim", {"runnerId": runner_id})
            run = claimed.get("run")
            if run:
                execute_run(api, run, runner_id, dry_run)
            elif once:
                return
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            print(f"runner error: {error}", flush=True)
            if once:
                raise SystemExit(1) from error
        if once:
            return
        time.sleep(max(poll_seconds, 0.5))


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Search Assistant automation runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--runner-id", default=f"{platform.node()}-automation-runner")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    run_loop(
        LocalApi(args.base_url),
        args.runner_id,
        dry_run=args.dry_run,
        once=args.once,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    main()
