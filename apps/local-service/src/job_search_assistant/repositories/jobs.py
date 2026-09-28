import hashlib
import json
import sqlite3
from pathlib import Path

from ..domain.models import CapturedJob, StoredJob


class JobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    platform_job_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    location TEXT,
                    salary_text TEXT,
                    experience TEXT,
                    education TEXT,
                    description TEXT NOT NULL,
                    skills_json TEXT NOT NULL,
                    recruiter_name TEXT,
                    recruiter_title TEXT,
                    captured_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    UNIQUE(platform, platform_job_id, content_hash)
                )
                """
            )

    def save_many(self, jobs: list[CapturedJob]) -> list[str]:
        self.initialize()
        accepted: list[str] = []
        with self._connect() as connection:
            for job in jobs:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO job_postings (
                        platform, platform_job_id, url, title, company_name,
                        location, salary_text, experience, education, description,
                        skills_json, recruiter_name, recruiter_title, captured_at,
                        source, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.platform,
                        job.platform_job_id,
                        job.url,
                        job.title,
                        job.company_name,
                        job.location,
                        job.salary_text,
                        job.experience,
                        job.education,
                        job.description,
                        json.dumps(job.skills, ensure_ascii=False),
                        job.recruiter_name,
                        job.recruiter_title,
                        job.captured_at.isoformat(),
                        job.source,
                        self._content_hash(job),
                    ),
                )
                if cursor.rowcount > 0:
                    accepted.append(job.platform_job_id)
        return accepted

    def count(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM job_postings").fetchone()
        return int(row[0]) if row else 0

    def list_recent(self, limit: int = 100) -> list[StoredJob]:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM job_postings
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, snapshot_id: int) -> bool:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM job_postings WHERE id = ?",
                (snapshot_id,),
            )
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _content_hash(job: CapturedJob) -> str:
        content = "\n".join(
            [job.title, job.company_name, job.description, "|".join(job.skills)]
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredJob:
        return StoredJob(
            id=row["id"],
            platform=row["platform"],
            platform_job_id=row["platform_job_id"],
            url=row["url"],
            title=row["title"],
            company_name=row["company_name"],
            location=row["location"],
            salary_text=row["salary_text"],
            experience=row["experience"],
            education=row["education"],
            description=row["description"],
            skills=json.loads(row["skills_json"]),
            recruiter_name=row["recruiter_name"],
            recruiter_title=row["recruiter_title"],
            captured_at=row["captured_at"],
            source=row["source"],
            content_hash=row["content_hash"],
        )
