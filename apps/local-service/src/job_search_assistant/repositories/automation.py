import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..automation import AutomationRunStatus, ensure_transition


class AutomationRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                """
            )
            now = datetime.now(UTC).isoformat()
            connection.execute(
                """UPDATE automation_runs SET status = 'interrupted', updated_at = ?
                WHERE status IN ('running', 'paused', 'stopping')""",
                (now,),
            )
        self._initialized = True

    def create_run(self, config: dict[str, Any], target_count: int) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO automation_runs(
                    status, config_snapshot_json, target_count, created_at, updated_at
                ) VALUES ('draft', ?, ?, ?, ?)""",
                (json.dumps(config, ensure_ascii=False), target_count, now, now),
            )
            run_id = int(cursor.lastrowid)
            self._append_event(connection, run_id, "run-created", "info", {"target": target_count})
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> dict[str, Any]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM automation_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        result = dict(row)
        result["config_snapshot"] = json.loads(result.pop("config_snapshot_json"))
        return result

    def list_runs(self) -> list[dict[str, Any]]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM automation_runs ORDER BY id DESC"
                ).fetchall()
            ]
        return [self.get_run(run_id) for run_id in run_ids]

    def append_event(
        self,
        run_id: int,
        event_type: str,
        level: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.get_run(run_id)
        with sqlite3.connect(self.database_path) as connection:
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
        with sqlite3.connect(self.database_path) as connection:
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
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM automation_events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

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
