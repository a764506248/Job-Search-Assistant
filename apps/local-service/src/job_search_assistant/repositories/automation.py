import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..automation import AutomationRunStatus, ensure_transition
from ..database import db_connect
from ..domain.salary import normalize_salary_text


def _row_as_dict(row: Any) -> dict[str, Any]:
    """Normalize SQLite rows and PostgreSQL compatibility rows."""
    return row.as_dict() if hasattr(row, "as_dict") else dict(row)


class AutomationRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with db_connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    config_snapshot_json TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    current_keyword TEXT,
                    current_job_id TEXT,
                    stop_reason TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence),
                    FOREIGN KEY(run_id) REFERENCES automation_runs(id)
                );
                CREATE TABLE IF NOT EXISTS automation_actions (
                    idempotency_key TEXT PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES automation_runs(id)
                );
                CREATE TABLE IF NOT EXISTS automation_runners (
                    runner_id TEXT PRIMARY KEY,
                    heartbeat_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(connection, "automation_runs", "runner_id", "TEXT")
            self._ensure_column(connection, "automation_runs", "heartbeat_at", "TEXT")
            self._ensure_column(connection, "automation_runs", "approval_token", "TEXT")
            self._ensure_column(connection, "automation_runs", "user_id", "INTEGER NOT NULL DEFAULT 1")
            now = datetime.now(UTC).isoformat()
            legacy_failures = connection.execute(
                """SELECT id FROM automation_runs
                WHERE status = 'completed' AND success_count = 0 AND failure_count > 0"""
            ).fetchall()
            for (run_id,) in legacy_failures:
                connection.execute(
                    """UPDATE automation_runs SET status = 'failed', stop_reason = ?, updated_at = ?
                    WHERE id = ?""",
                    ("全部计划岗位处理失败", now, run_id),
                )
                self._append_event(
                    connection,
                    int(run_id),
                    "status-corrected",
                    "warning",
                    {
                        "from": "completed",
                        "to": "failed",
                        "reason": "历史任务全部岗位失败，已修正任务状态",
                    },
                )
            connection.execute(
                """UPDATE automation_runs SET status = 'interrupted', updated_at = ?
                WHERE status IN ('running', 'paused', 'stopping')""",
                (now,),
            )
        self._initialized = True

    def create_run(self, config: dict[str, Any], target_count: int, *, user_id: int = 1) -> dict[str, Any]:
        self.initialize()
        config = self._normalize_config(config)
        # Confirmation evidence is server-owned.  A client may provide a draft
        # plan, but it cannot mark that plan as approved while creating it.
        config.pop("planConfirmation", None)
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO automation_runs(
                    user_id, status, config_snapshot_json, target_count, created_at, updated_at
                ) VALUES (?, 'draft', ?, ?, ?, ?) RETURNING id""",
                (user_id, json.dumps(config, ensure_ascii=False), target_count, now, now),
            )
            run_id = int(cursor.lastrowid)
            self._append_event(connection, run_id, "run-created", "info", {"target": target_count})
        return self.get_run(run_id)

    def get_run(self, run_id: int, *, user_id: int | None = None) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            sql = "SELECT * FROM automation_runs WHERE id = ?"
            params: tuple[Any, ...] = (run_id,)
            if user_id is not None:
                sql += " AND user_id = ?"
                params = (run_id, user_id)
            row = connection.execute(sql, params).fetchone()
        if row is None:
            raise KeyError(run_id)
        result = row.as_dict() if hasattr(row, "as_dict") else dict(row)
        # The capability is intentionally excluded from ordinary run reads.  It
        # is exposed only by claim_next_run to the host runner.
        result.pop("approval_token", None)
        result["config_snapshot"] = self._normalize_config(
            json.loads(result.pop("config_snapshot_json"))
        )
        return result

    def confirm_plan(
        self, run_id: int, planned_jobs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Freeze the user-confirmed subset before any runner can claim the task."""
        run = self.get_run(run_id)
        if run["status"] != "draft":
            raise ValueError(f"run plan cannot be confirmed from {run['status']}")
        config = dict(run["config_snapshot"])
        normalized_jobs = self._normalize_planned_jobs(planned_jobs)
        selected_job_ids = [str(job.get("jobId", "")) for job in normalized_jobs]
        if not selected_job_ids or any(not job_id for job_id in selected_job_ids):
            raise ValueError("confirmed plan requires job ids")
        if len(selected_job_ids) != len(set(selected_job_ids)):
            raise ValueError("confirmed plan contains duplicate job ids")
        now = datetime.now(UTC).isoformat()
        config["plannedJobs"] = normalized_jobs
        config["planConfirmation"] = {
            "status": "confirmed",
            "source": "selected-job-list",
            "confirmedAt": now,
            "selectedJobIds": selected_job_ids,
        }
        approval_token = secrets.token_urlsafe(32)
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE automation_runs SET config_snapshot_json = ?, target_count = ?,
                approval_token = ?, updated_at = ? WHERE id = ?""",
                (
                    json.dumps(config, ensure_ascii=False),
                    len(normalized_jobs),
                    approval_token,
                    now,
                    run_id,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "plan-confirmed",
                "info",
                {
                    "selectedCount": len(normalized_jobs),
                    "companies": [job.get("companyName", "") for job in normalized_jobs],
                },
            )
        return self.get_run(run_id)

    def update_collection(
        self,
        run_id: int,
        state: str,
        *,
        planned_jobs: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
        emit_event: bool = True,
    ) -> dict[str, Any]:
        """Persist extension collection progress while the run is still a draft."""
        run = self.get_run(run_id)
        if run["status"] != "draft":
            raise ValueError(f"run collection cannot be updated from {run['status']}")
        config = dict(run["config_snapshot"])
        collection = dict(config.get("collection") or {})
        collection.update(details or {})
        collection["status"] = state
        collection["updatedAt"] = datetime.now(UTC).isoformat()
        config["collection"] = collection
        if planned_jobs is not None:
            config["plannedJobs"] = self._normalize_planned_jobs(planned_jobs)

        event_type = {
            "pending": "collection-queued",
            "collecting": "collection-started",
            "ready": "collection-finished",
            "no_matches": "analysis-finished",
            "failed": "collection-failed",
            "cancelled": "collection-cancelled",
        }.get(state, "collection-updated")
        level = "error" if state == "failed" else "warning" if state == "cancelled" else "info"
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE automation_runs SET config_snapshot_json = ?, updated_at = ?
                WHERE id = ?""",
                (json.dumps(config, ensure_ascii=False), now, run_id),
            )
            if emit_event:
                self._append_event(
                    connection,
                    run_id,
                    event_type,
                    level,
                    {"state": state, **(details or {})},
                )
        return self.get_run(run_id)

    def approval_token_matches(self, run_id: int, supplied_token: str) -> bool:
        """Validate the runner capability without exposing its stored value."""
        if not supplied_token:
            return False
        stored_token = self._approval_token(run_id)
        return bool(
            stored_token
            and secrets.compare_digest(stored_token, supplied_token)
        )

    def _approval_token(self, run_id: int) -> str | None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT approval_token FROM automation_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return str(row[0]) if row[0] else None

    def claim_next_run(self, runner_id: str, *, user_id: int) -> dict[str, Any] | None:
        """Atomically claim the oldest runnable task owned by the connected user."""
        self.initialize()
        self.interrupt_stale_runs()
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.row_factory = sqlite3.Row
            self._upsert_runner(connection, runner_id, now)
            claim_sql = """SELECT id FROM automation_runs
                WHERE status = 'running' AND runner_id IS NULL AND user_id = ?
                ORDER BY id LIMIT 1"""
            if getattr(connection, "is_postgres", False):
                claim_sql += " FOR UPDATE SKIP LOCKED"
            row = connection.execute(claim_sql, (user_id,)).fetchone()
            if row is None:
                return None
            run_id = int(row["id"])
            updated = connection.execute(
                """UPDATE automation_runs SET runner_id = ?, heartbeat_at = ?, updated_at = ?
                WHERE id = ? AND runner_id IS NULL AND user_id = ?""",
                (runner_id, now, now, run_id, user_id),
            )
            if updated.rowcount != 1:
                return None
            self._append_event(
                connection,
                run_id,
                "runner-claimed",
                "info",
                {"runnerId": runner_id},
            )
        claimed = self.get_run(run_id)
        claimed["approval_token"] = self._approval_token(run_id)
        return claimed

    def interrupt_stale_runs(self, max_age_seconds: int = 180) -> list[int]:
        """Release runs whose owning worker stopped updating the run heartbeat."""
        self.initialize()
        now = datetime.now(UTC)
        cutoff = (now - timedelta(seconds=max_age_seconds)).isoformat()
        interrupted: list[int] = []
        reason = "执行器任务心跳超时，任务已中断，可重新执行"
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT id, status, runner_id FROM automation_runs
                WHERE status IN ('running', 'paused', 'stopping')
                AND runner_id IS NOT NULL
                AND heartbeat_at IS NOT NULL
                AND heartbeat_at < ?""",
                (cutoff,),
            ).fetchall()
            for row in rows:
                run_id = int(row["id"])
                updated = connection.execute(
                    """UPDATE automation_runs
                    SET status = 'interrupted', runner_id = NULL,
                        stop_reason = ?, updated_at = ?
                    WHERE id = ? AND status IN ('running', 'paused', 'stopping')
                    AND runner_id = ? AND heartbeat_at < ?""",
                    (reason, now.isoformat(), run_id, str(row["runner_id"]), cutoff),
                )
                if updated.rowcount != 1:
                    continue
                interrupted.append(run_id)
                self._append_event(
                    connection,
                    run_id,
                    "status-changed",
                    "warning",
                    {
                        "from": str(row["status"]),
                        "to": "interrupted",
                        "reason": reason,
                    },
                )
        return interrupted

    def runner_heartbeat(self, runner_id: str) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            self._upsert_runner(connection, runner_id, now)
        return {"runner_id": runner_id, "heartbeat_at": now, "online": True}

    def runner_status(self, max_age_seconds: int = 30) -> dict[str, Any]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT runner_id, heartbeat_at FROM automation_runners "
                "ORDER BY heartbeat_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {"runner_id": None, "heartbeat_at": None, "online": False}
        heartbeat_at = datetime.fromisoformat(str(row["heartbeat_at"]))
        online = datetime.now(UTC) - heartbeat_at <= timedelta(seconds=max_age_seconds)
        return {
            "runner_id": str(row["runner_id"]),
            "heartbeat_at": str(row["heartbeat_at"]),
            "online": online,
        }

    def heartbeat(self, run_id: int, runner_id: str) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE automation_runs SET heartbeat_at = ?, updated_at = ?
                WHERE id = ? AND runner_id = ?""",
                (now, now, run_id, runner_id),
            )
            if cursor.rowcount != 1:
                raise PermissionError("automation run is not claimed by this runner")
        return self.get_run(run_id)

    def record_progress(
        self,
        run_id: int,
        job_id: str,
        outcome: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.get_run(run_id)
        success_delta = 1 if outcome == "success" else 0
        failure_delta = 1 if outcome == "failure" else 0
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE automation_runs SET current_job_id = ?,
                success_count = success_count + ?, failure_count = failure_count + ?,
                updated_at = ? WHERE id = ?""",
                (job_id, success_delta, failure_delta, now, run_id),
            )
            self._append_event(
                connection,
                run_id,
                "job-finished",
                "info" if outcome == "success" else "warning",
                {"jobId": job_id, "outcome": outcome, "reason": reason},
            )
        return self.get_run(run_id)

    def claim_action(
        self,
        run_id: int,
        job_id: str,
        action_type: str,
    ) -> tuple[dict[str, Any], bool]:
        """Create or retry an action and report whether a side effect may execute."""
        self.get_run(run_id)
        idempotency_key = f"{run_id}:{job_id}:{action_type}"
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM automation_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None and existing["status"] in {
                "pending",
                "succeeded",
                "uncertain",
            }:
                return (existing.as_dict() if hasattr(existing, "as_dict") else dict(existing)), False
            if existing is None:
                connection.execute(
                    """INSERT INTO automation_actions(
                        idempotency_key, run_id, job_id, action_type, status,
                        attempt_count, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', 1, ?)""",
                    (idempotency_key, run_id, job_id, action_type, now),
                )
            else:
                connection.execute(
                    """UPDATE automation_actions SET status = 'pending',
                    attempt_count = attempt_count + 1, last_error = NULL, updated_at = ?
                    WHERE idempotency_key = ?""",
                    (now, idempotency_key),
                )
            self._append_event(
                connection,
                run_id,
                "action-claimed",
                "info",
                {"jobId": job_id, "actionType": action_type, "idempotencyKey": idempotency_key},
            )
            row = connection.execute(
                "SELECT * FROM automation_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return (row.as_dict() if hasattr(row, "as_dict") else dict(row)), True

    def finish_action(
        self,
        idempotency_key: str,
        *,
        succeeded: bool | None,
        error: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM automation_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise KeyError(idempotency_key)
            status = "uncertain" if succeeded is None else ("succeeded" if succeeded else "failed")
            connection.execute(
                """UPDATE automation_actions SET status = ?, last_error = ?, updated_at = ?
                WHERE idempotency_key = ?""",
                (status, error, now, idempotency_key),
            )
            self._append_event(
                connection,
                int(row["run_id"]),
                "action-finished",
                "warning" if succeeded is None else ("info" if succeeded else "error"),
                {
                    "jobId": row["job_id"],
                    "actionType": row["action_type"],
                    "idempotencyKey": idempotency_key,
                    "status": status,
                    "error": error,
                    "evidence": evidence or {},
                },
            )
            result = connection.execute(
                "SELECT * FROM automation_actions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if result is None:  # pragma: no cover - the action was read in this transaction
            raise KeyError(idempotency_key)
        return _row_as_dict(result)

    def list_actions(self, run_id: int) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM automation_actions WHERE run_id = ? ORDER BY updated_at",
                (run_id,),
            ).fetchall()
        return [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in rows]

    def report(self, run_id: int, *, user_id: int | None = None) -> dict[str, Any]:
        run = self.get_run(run_id, user_id=user_id)
        return {
            "run": run,
            "actions": self.list_actions(run_id),
            "events": self.list_events(run_id),
        }

    def list_runs(self, user_id: int | None = None) -> list[dict[str, Any]]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            query = "SELECT id FROM automation_runs"
            params: tuple[Any, ...] = ()
            if user_id is not None:
                query += " WHERE user_id = ?"
                params = (user_id,)
            query += " ORDER BY id DESC"
            run_ids = [row[0] for row in connection.execute(query, params).fetchall()]
        return [self.get_run(run_id) for run_id in run_ids]

    def append_event(
        self,
        run_id: int,
        event_type: str,
        level: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.get_run(run_id)
        with db_connect(self.database_path) as connection:
            self._append_event(connection, run_id, event_type, level, payload)
        return self.list_events(run_id)[-1]

    def transition(
        self, run_id: int, target: AutomationRunStatus | str, reason: str | None = None
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        target_status = ensure_transition(run["status"], target)
        now = datetime.now(UTC).isoformat()
        started_at = run["started_at"]
        if target_status == AutomationRunStatus.RUNNING and not started_at:
            started_at = now
        finished_at = now if target_status in {
            AutomationRunStatus.COMPLETED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.BLOCKED,
            AutomationRunStatus.CANCELLED,
        } else run["finished_at"]
        with db_connect(self.database_path) as connection:
            connection.execute(
                """UPDATE automation_runs SET status = ?, stop_reason = ?, started_at = ?,
                finished_at = ?, updated_at = ? WHERE id = ?""",
                (target_status, reason, started_at, finished_at, now, run_id),
            )
            self._append_event(
                connection,
                run_id,
                "status-changed",
                (
                    "warning"
                    if target_status
                    in {AutomationRunStatus.BLOCKED, AutomationRunStatus.FAILED}
                    else "info"
                ),
                {"from": run["status"], "to": target_status, "reason": reason},
            )
        return self.get_run(run_id)

    def list_events(self, run_id: int) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM automation_events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [{**(row.as_dict() if hasattr(row, "as_dict") else dict(row)), "payload": json.loads(row["payload_json"])} for row in rows]

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        run_id: int,
        event_type: str,
        level: str,
        payload: dict[str, Any],
    ) -> None:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM automation_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO automation_events(
                run_id, sequence, event_type, level, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                sequence,
                event_type,
                level,
                json.dumps(payload, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
            ),
        )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @classmethod
    def _normalize_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(config)
        planned_jobs = normalized.get("plannedJobs")
        if isinstance(planned_jobs, list):
            normalized["plannedJobs"] = cls._normalize_planned_jobs(planned_jobs)
        return normalized

    @staticmethod
    def _normalize_planned_jobs(
        planned_jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_jobs: list[dict[str, Any]] = []
        for item in planned_jobs:
            if not isinstance(item, dict):
                continue
            job = dict(item)
            if "salaryText" in job:
                job["salaryText"] = normalize_salary_text(
                    str(job["salaryText"]) if job["salaryText"] is not None else None
                )
            normalized_jobs.append(job)
        return normalized_jobs

    @staticmethod
    def _upsert_runner(
        connection: sqlite3.Connection,
        runner_id: str,
        heartbeat_at: str,
    ) -> None:
        connection.execute(
            """INSERT INTO automation_runners(runner_id, heartbeat_at) VALUES (?, ?)
            ON CONFLICT(runner_id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at""",
            (runner_id, heartbeat_at),
        )
