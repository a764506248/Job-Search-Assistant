import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..database import db_connect
from typing import Any


class ClientLogRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with db_connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS client_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    page_url TEXT,
                    platform_job_id TEXT,
                    details_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_client_logs_received
                ON client_logs(received_at DESC)"""
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        received_at = datetime.now(UTC).isoformat()
        with db_connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO client_logs(
                    source, level, event, message, page_url, platform_job_id,
                    details_json, occurred_at, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["source"],
                    data["level"],
                    data["event"],
                    data["message"],
                    data.get("page_url"),
                    data.get("platform_job_id"),
                    json.dumps(data.get("details", {}), ensure_ascii=False),
                    data["occurred_at"].isoformat(),
                    received_at,
                ),
            )
            log_id = int(cursor.lastrowid)
        return {"id": log_id, **data, "received_at": received_at}

    def list_recent(self, limit: int) -> list[dict[str, Any]]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM client_logs ORDER BY received_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "source": row["source"],
                "level": row["level"],
                "event": row["event"],
                "message": row["message"],
                "page_url": row["page_url"],
                "platform_job_id": row["platform_job_id"],
                "details": json.loads(row["details_json"]),
                "occurred_at": row["occurred_at"],
                "received_at": row["received_at"],
            }
            for row in rows
        ]
