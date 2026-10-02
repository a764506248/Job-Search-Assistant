#!/usr/bin/env python3
"""Host companion for automation tasks.

The runner never talks to the page directly. Every browser operation goes through
the local service's allow-listed, idempotent browser-action endpoint.
"""

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


def browser_action(
    api: LocalApi,
    run_id: int,
    runner_id: str,
    *,
    job_id: str,
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return api.post(
        f"/v1/automation/runs/{run_id}/browser-action",
        {
            "runnerId": runner_id,
            "jobId": job_id,
            "action": action,
            "payload": payload,
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


def execute_run(api: LocalApi, run: dict[str, Any], runner_id: str, dry_run: bool) -> None:
    run_id = int(run["id"])
    config = run.get("configSnapshot", {})
    api.post(f"/v1/automation/runs/{run_id}/heartbeat", {"runnerId": runner_id})
    if dry_run:
        api.post(
            f"/v1/automation/runs/{run_id}/runner-finish",
            {
                "runnerId": runner_id,
                "status": "completed",
                "reason": "host-runner-dry-run",
            },
        )
        return

    planned_jobs = config.get("plannedJobs", [])
    if not isinstance(planned_jobs, list) or not planned_jobs:
        api.post(
            f"/v1/automation/runs/{run_id}/runner-finish",
            {
                "runnerId": runner_id,
                "status": "blocked",
                "reason": "没有服务端已审批的岗位计划；未执行浏览器副作用",
            },
        )
        return

    for job in planned_jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("jobId", ""))
        expected_title = str(job.get("title", ""))
        expected_company = str(job.get("companyName", ""))
        greeting = str(job.get("greeting", ""))
        job_url = str(job.get("url", ""))
        if not all((job_id, job_url, expected_title, expected_company, greeting)):
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
            record_progress(api, run_id, runner_id, job_id, "failure", "open-job-failed")
            continue
        time.sleep(2)
        chat = browser_action(
            api,
            run_id,
            runner_id,
            job_id=job_id,
            action="open_chat",
            payload={"expectedTitle": expected_title, "expectedCompany": expected_company},
        )
        if chat.get("result", {}).get("status") != "success":
            record_progress(api, run_id, runner_id, job_id, "failure", "open-chat-failed")
            continue
        identity = browser_action(
            api,
            run_id,
            runner_id,
            job_id=job_id,
            action="validate_identity",
            payload={"expectedTitle": expected_title, "expectedCompany": expected_company},
        )
        if identity.get("result", {}).get("status") != "success":
            record_progress(api, run_id, runner_id, job_id, "failure", "identity-mismatch")
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
        )
        greeting_status = sent.get("result", {}).get("status")
        if greeting_status != "success":
            record_progress(
                api, run_id, runner_id, job_id, "failure", f"greeting-{greeting_status}"
            )
            api.post(
                f"/v1/automation/runs/{run_id}/runner-finish",
                {
                    "runnerId": runner_id,
                    "status": "blocked",
                    "reason": f"问候语发送未确认成功：{greeting_status or 'unknown'}",
                },
            )
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
            )
            resume_status = resume.get("result", {}).get("status")
            if resume_status != "success":
                record_progress(
                    api, run_id, runner_id, job_id, "failure", f"resume-{resume_status}"
                )
                api.post(
                    f"/v1/automation/runs/{run_id}/runner-finish",
                    {
                        "runnerId": runner_id,
                        "status": "blocked",
                        "reason": f"简历发送未确认成功：{resume_status or 'unknown'}",
                    },
                )
                return
        record_progress(api, run_id, runner_id, job_id, "success", "delivery-confirmed")

    api.post(
        f"/v1/automation/runs/{run_id}/runner-finish",
        {"runnerId": runner_id, "status": "completed", "reason": "plan-finished"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Search Assistant host runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--runner-id", default=f"{platform.node()}-host-runner")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    api = LocalApi(args.base_url)
    while True:
        try:
            claimed = api.post("/v1/automation/runner/claim", {"runnerId": args.runner_id})
            run = claimed.get("run")
            if run:
                execute_run(api, run, args.runner_id, args.dry_run)
            elif args.once:
                return
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            print(f"runner error: {error}", flush=True)
            if args.once:
                raise SystemExit(1) from error
        if args.once:
            return
        time.sleep(max(args.poll_seconds, 0.5))


if __name__ == "__main__":
    main()
