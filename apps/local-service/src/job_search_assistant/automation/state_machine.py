from enum import StrEnum


class AutomationRunStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


TRANSITIONS: dict[AutomationRunStatus, frozenset[AutomationRunStatus]] = {
    AutomationRunStatus.DRAFT: frozenset(
        {AutomationRunStatus.VALIDATING, AutomationRunStatus.CANCELLED}
    ),
    AutomationRunStatus.VALIDATING: frozenset(
        {
            AutomationRunStatus.READY,
            AutomationRunStatus.BLOCKED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.CANCELLED,
        }
    ),
    AutomationRunStatus.READY: frozenset(
        {AutomationRunStatus.RUNNING, AutomationRunStatus.CANCELLED}
    ),
    AutomationRunStatus.RUNNING: frozenset(
        {
            AutomationRunStatus.PAUSED,
            AutomationRunStatus.STOPPING,
            AutomationRunStatus.COMPLETED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.BLOCKED,
            AutomationRunStatus.INTERRUPTED,
        }
    ),
    AutomationRunStatus.PAUSED: frozenset(
        {
            AutomationRunStatus.RUNNING,
            AutomationRunStatus.STOPPING,
            AutomationRunStatus.CANCELLED,
            AutomationRunStatus.INTERRUPTED,
        }
    ),
    AutomationRunStatus.STOPPING: frozenset(
        {
            AutomationRunStatus.COMPLETED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.CANCELLED,
            AutomationRunStatus.INTERRUPTED,
        }
    ),
    AutomationRunStatus.INTERRUPTED: frozenset(
        {AutomationRunStatus.RUNNING, AutomationRunStatus.CANCELLED}
    ),
    AutomationRunStatus.COMPLETED: frozenset(),
    AutomationRunStatus.FAILED: frozenset(),
    AutomationRunStatus.BLOCKED: frozenset(),
    AutomationRunStatus.CANCELLED: frozenset(),
}


def ensure_transition(
    current: AutomationRunStatus | str,
    target: AutomationRunStatus | str,
) -> AutomationRunStatus:
    current_status = AutomationRunStatus(current)
    target_status = AutomationRunStatus(target)
    if target_status not in TRANSITIONS[current_status]:
        raise ValueError(f"invalid automation transition: {current_status} -> {target_status}")
    return target_status


def is_terminal(status: AutomationRunStatus | str) -> bool:
    return not TRANSITIONS[AutomationRunStatus(status)]
