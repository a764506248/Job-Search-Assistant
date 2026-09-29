import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..domain.models import DeliveryRecord, DeliveryRecordInput


class DeliveryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    platform_job_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    salary_text TEXT,
                    location TEXT,
                    recruiter_name TEXT,
                    status TEXT NOT NULL,
                    decision TEXT,
                    reason TEXT,
                    greeting_text TEXT,
                    detail TEXT,
                    applied_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, platform_job_id)
                )
                """
            )

    def upsert(self, delivery: DeliveryRecordInput) -> DeliveryRecord:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO delivery_records (
                    platform, platform_job_id, title, company_name, salary_text,
                    location, recruiter_name, status, decision, reason,
                    greeting_text, detail, applied_at, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, platform_job_id) DO UPDATE SET
                    title = excluded.title,
                    company_name = excluded.company_name,
                    salary_text = excluded.salary_text,
                    location = excluded.location,
                    recruiter_name = excluded.recruiter_name,
                    status = excluded.status,
                    decision = excluded.decision,
                    reason = excluded.reason,
                    greeting_text = excluded.greeting_text,
                    detail = excluded.detail,
                    applied_at = excluded.applied_at,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    delivery.platform,
                    delivery.platform_job_id,
                    delivery.title,
                    delivery.company_name,
                    delivery.salary_text,
                    delivery.location,
                    delivery.recruiter_name,
                    delivery.status,
                    delivery.decision,
                    delivery.reason,
                    delivery.greeting_text,
                    delivery.detail,
                    delivery.applied_at.isoformat(),
                    json.dumps(delivery.metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT * FROM delivery_records
                WHERE platform = ? AND platform_job_id = ?
                """,
                (delivery.platform, delivery.platform_job_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("delivery record was not persisted")
        return self._from_row(row)

    def count(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM delivery_records").fetchone()
        return int(row[0]) if row else 0

    def list_recent(self, limit: int = 100) -> list[DeliveryRecord]:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM delivery_records
                ORDER BY applied_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DeliveryRecord:
        return DeliveryRecord(
            id=row["id"],
            platform=row["platform"],
            platform_job_id=row["platform_job_id"],
            title=row["title"],
            company_name=row["company_name"],
            salary_text=row["salary_text"],
            location=row["location"],
            recruiter_name=row["recruiter_name"],
            status=row["status"],
            decision=row["decision"],
            reason=row["reason"],
            greeting_text=row["greeting_text"],
            detail=row["detail"],
            applied_at=row["applied_at"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
