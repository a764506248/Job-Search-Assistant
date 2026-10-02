import pytest

from job_search_assistant.automation import (
    AutomationRunStatus,
    ensure_transition,
    is_terminal,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "validating"),
        ("validating", "ready"),
        ("ready", "running"),
        ("running", "paused"),
        ("paused", "running"),
        ("running", "stopping"),
        ("stopping", "completed"),
        ("running", "interrupted"),
        ("interrupted", "running"),
        ("interrupted", "blocked"),
    ],
)
def test_valid_automation_transitions(current: str, target: str) -> None:
    assert ensure_transition(current, target) == AutomationRunStatus(target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "running"),
        ("ready", "completed"),
        ("paused", "completed"),
        ("completed", "running"),
        ("blocked", "validating"),
        ("cancelled", "draft"),
    ],
)
def test_invalid_automation_transitions_are_rejected(current: str, target: str) -> None:
    with pytest.raises(ValueError, match="invalid automation transition"):
        ensure_transition(current, target)


def test_terminal_statuses_cannot_transition() -> None:
    assert is_terminal("completed") is True
    assert is_terminal("failed") is True
    assert is_terminal("blocked") is True
    assert is_terminal("cancelled") is True
    assert is_terminal("running") is False
