from job_search_assistant.repositories import AutomationRepository


def test_automation_run_persists_transitions_and_events(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")
    run = repository.create_run({"keywords": ["AI Agent"]}, 20)

    assert run["status"] == "draft"
    repository.transition(run["id"], "validating")
    repository.transition(run["id"], "ready")
    running = repository.transition(run["id"], "running")
    paused = repository.transition(run["id"], "paused")

    assert running["started_at"]
    assert paused["status"] == "paused"
    assert [event["sequence"] for event in repository.list_events(run["id"])] == [1, 2, 3, 4, 5]


def test_plan_confirmation_is_server_owned_and_issues_runner_capability(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")
    run = repository.create_run(
        {
            "plannedJobs": [{"jobId": "draft-job"}],
            "planConfirmation": {
                "status": "confirmed",
                "approvalToken": "client-forged-token",
            },
        },
        1,
    )

    assert "planConfirmation" not in run["config_snapshot"]

    confirmed = repository.confirm_plan(
        run["id"],
        [
            {
                "jobId": "job-1",
                "title": "AI 工程师",
                "companyName": "示例公司",
                "greeting": "您好",
            }
        ],
    )
    evidence = confirmed["config_snapshot"]["planConfirmation"]

    assert evidence["status"] == "confirmed"
    assert evidence["source"] == "selected-job-list"
    assert evidence["selectedJobIds"] == ["job-1"]
    assert "approvalToken" not in evidence
    assert "approval_token" not in repository.get_run(run["id"])
    assert "approvalToken" not in repository.list_events(run["id"])[-1]["payload"]

    repository.transition(run["id"], "validating")
    repository.transition(run["id"], "ready")
    repository.transition(run["id"], "running")
    claimed = repository.claim_next_run("runner-a")
    assert claimed is not None
    assert claimed["approval_token"]
    assert claimed["approval_token"] != "client-forged-token"
    assert repository.approval_token_matches(
        run["id"], claimed["approval_token"]
    )


def test_active_run_becomes_interrupted_after_repository_restart(tmp_path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    repository = AutomationRepository(database_path)
    run = repository.create_run({}, 5)
    repository.transition(run["id"], "validating")
    repository.transition(run["id"], "ready")
    repository.transition(run["id"], "running")

    restarted = AutomationRepository(database_path)
    restarted.initialize()

    assert restarted.get_run(run["id"])["status"] == "interrupted"


def test_runner_claim_is_atomic_and_action_is_idempotent(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")
    run = repository.create_run({"keywords": ["AI Agent"]}, 1)
    repository.transition(run["id"], "validating")
    repository.transition(run["id"], "ready")
    repository.transition(run["id"], "running")

    claimed = repository.claim_next_run("runner-a")
    assert claimed is not None
    assert claimed["runner_id"] == "runner-a"
    assert repository.claim_next_run("runner-b") is None
    assert repository.heartbeat(run["id"], "runner-a")["heartbeat_at"]
    progress = repository.record_progress(run["id"], "job-1", "success", "confirmed")
    assert progress["success_count"] == 1
    assert progress["current_job_id"] == "job-1"

    action, execute = repository.claim_action(run["id"], "job-1", "send-greeting")
    duplicate, duplicate_execute = repository.claim_action(
        run["id"], "job-1", "send-greeting"
    )
    assert execute is True
    assert duplicate_execute is False
    assert duplicate["idempotency_key"] == action["idempotency_key"]

    completed = repository.finish_action(
        action["idempotency_key"],
        succeeded=True,
        evidence={"messageBubbleObserved": True},
    )
    assert completed["status"] == "succeeded"
    _, after_success_execute = repository.claim_action(
        run["id"], "job-1", "send-greeting"
    )
    assert after_success_execute is False
    assert repository.report(run["id"])["actions"][0]["attempt_count"] == 1


def test_runner_heartbeat_reports_worker_online(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")

    assert repository.runner_status()["online"] is False
    heartbeat = repository.runner_heartbeat("runner-a")

    assert heartbeat["online"] is True
    assert repository.runner_status()["runner_id"] == "runner-a"


def test_repository_corrects_legacy_all_failed_completed_run(tmp_path) -> None:
    database_path = tmp_path / "automation.db"
    repository = AutomationRepository(database_path)
    run = repository.create_run({"plannedJobs": [{"jobId": "job-1"}]}, 1)
    repository.transition(run["id"], "validating")
    repository.transition(run["id"], "ready")
    repository.transition(run["id"], "running")
    repository.record_progress(run["id"], "job-1", "failure", "identity-mismatch")
    repository.transition(run["id"], "completed", "plan-finished")

    reloaded = AutomationRepository(database_path)
    corrected = reloaded.get_run(run["id"])

    assert corrected["status"] == "failed"
    assert corrected["stop_reason"] == "全部计划岗位处理失败"
    assert reloaded.list_events(run["id"])[-1]["event_type"] == "status-corrected"


def test_failed_action_can_be_retried(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")
    run = repository.create_run({}, 1)
    action, _ = repository.claim_action(run["id"], "job-2", "open-job")
    repository.finish_action(action["idempotency_key"], succeeded=False, error="timeout")

    retried, execute = repository.claim_action(run["id"], "job-2", "open-job")

    assert execute is True
    assert retried["status"] == "pending"
    assert retried["attempt_count"] == 2


def test_uncertain_action_is_never_retried_automatically(tmp_path) -> None:
    repository = AutomationRepository(tmp_path / "jobs.sqlite3")
    run = repository.create_run({}, 1)
    action, _ = repository.claim_action(run["id"], "job-3", "send-greeting")
    repository.finish_action(
        action["idempotency_key"],
        succeeded=None,
        error="send clicked but delivery evidence incomplete",
    )

    uncertain, execute = repository.claim_action(run["id"], "job-3", "send-greeting")

    assert uncertain["status"] == "uncertain"
    assert execute is False
    assert uncertain["attempt_count"] == 1
