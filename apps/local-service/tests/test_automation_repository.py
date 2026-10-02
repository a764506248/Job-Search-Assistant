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
