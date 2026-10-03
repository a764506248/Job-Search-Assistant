import hashlib
import json
import sqlite3
from pathlib import Path

from ..domain.models import CapturedJob, StoredJob
from ..domain.salary import normalize_salary_text, prefer_salary_text


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
                    company_size TEXT,
                    location TEXT,
                    work_address TEXT,
                    salary_text TEXT,
                    experience TEXT,
                    education TEXT,
                    description TEXT NOT NULL,
                    skills_json TEXT NOT NULL,
                    recruiter_name TEXT,
                    recruiter_title TEXT,
                    has_communicated INTEGER NOT NULL DEFAULT 0,
                    has_interview INTEGER NOT NULL DEFAULT 0,
                    generated_greeting TEXT,
                    resume_variant TEXT NOT NULL DEFAULT 'default',
                    generated_resume_id INTEGER,
                    resume_optimization TEXT,
                    captured_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    UNIQUE(platform, platform_job_id, content_hash)
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(job_postings)")}
            migrations = {
                "has_communicated": "INTEGER NOT NULL DEFAULT 0",
                "has_interview": "INTEGER NOT NULL DEFAULT 0",
                "generated_greeting": "TEXT",
                "resume_variant": "TEXT NOT NULL DEFAULT 'default'",
                "generated_resume_id": "INTEGER",
                "resume_optimization": "TEXT",
                "company_size": "TEXT",
                "work_address": "TEXT",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE job_postings ADD COLUMN {name} {definition}"
                    )
            self._deduplicate_existing(connection)
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS
                idx_job_postings_platform_job_id
                ON job_postings(platform, platform_job_id)"""
            )

    def save_many(self, jobs: list[CapturedJob]) -> list[str]:
        self.initialize()
        accepted: list[str] = []
        with self._connect() as connection:
            for job in jobs:
                content_hash = self._content_hash(job)
                existing = connection.execute(
                    """SELECT salary_text FROM job_postings
                    WHERE platform = ? AND platform_job_id = ?""",
                    (job.platform, job.platform_job_id),
                ).fetchone()
                salary_text = prefer_salary_text(
                    existing[0] if existing is not None else None,
                    job.salary_text,
                )
                cursor = connection.execute(
                    """
                    INSERT INTO job_postings (
                        platform, platform_job_id, url, title, company_name, company_size,
                        location, work_address, salary_text, experience, education, description,
                        skills_json, recruiter_name, recruiter_title, captured_at,
                        has_communicated, has_interview, generated_greeting,
                        resume_variant, generated_resume_id, resume_optimization,
                        source, content_hash
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(platform, platform_job_id) DO UPDATE SET
                        url = excluded.url,
                        title = excluded.title,
                        company_name = excluded.company_name,
                        company_size = COALESCE(excluded.company_size, job_postings.company_size),
                        location = COALESCE(excluded.location, job_postings.location),
                        work_address = COALESCE(
                            excluded.work_address, job_postings.work_address
                        ),
                        salary_text = COALESCE(excluded.salary_text, job_postings.salary_text),
                        experience = COALESCE(excluded.experience, job_postings.experience),
                        education = COALESCE(excluded.education, job_postings.education),
                        skills_json = CASE
                            WHEN excluded.skills_json != '[]' THEN excluded.skills_json
                            ELSE job_postings.skills_json
                        END,
                        recruiter_name = COALESCE(
                            excluded.recruiter_name, job_postings.recruiter_name
                        ),
                        recruiter_title = COALESCE(
                            excluded.recruiter_title, job_postings.recruiter_title
                        ),
                        generated_greeting = CASE
                            WHEN excluded.content_hash != job_postings.content_hash
                                THEN excluded.generated_greeting
                            ELSE COALESCE(
                                excluded.generated_greeting,
                                job_postings.generated_greeting
                            )
                        END,
                        description = excluded.description,
                        captured_at = excluded.captured_at,
                        source = excluded.source,
                        content_hash = excluded.content_hash
                    """,
                    (
                        job.platform,
                        job.platform_job_id,
                        job.url,
                        job.title,
                        job.company_name,
                        job.company_size,
                        job.location,
                        job.work_address,
                        salary_text,
                        job.experience,
                        job.education,
                        job.description,
                        json.dumps(job.skills, ensure_ascii=False),
                        job.recruiter_name,
                        job.recruiter_title,
                        job.captured_at.isoformat(),
                        int(job.has_communicated),
                        int(job.has_interview),
                        job.generated_greeting,
                        job.resume_variant,
                        job.generated_resume_id,
                        job.resume_optimization,
                        job.source,
                        content_hash,
                    ),
                )
                if cursor.rowcount > 0 and existing is None:
                    accepted.append(job.platform_job_id)
        return accepted

    def get_by_platform_job_id(self, platform: str, platform_job_id: str) -> StoredJob:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT * FROM job_postings
                WHERE platform = ? AND platform_job_id = ?""",
                (platform, platform_job_id),
            ).fetchone()
        if row is None:
            raise KeyError(platform_job_id)
        return self._from_row(row)

    def list_platform_job_ids(self, platform: str) -> list[str]:
        """Return stable ids so browser collection can skip locally known jobs."""
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT platform_job_id FROM job_postings
                WHERE platform = ? ORDER BY id""",
                (platform,),
            ).fetchall()
        return [str(row[0]) for row in rows if row[0]]

    def count(
        self, query: str | None = None, communication_result: str | None = None
    ) -> int:
        self.initialize()
        where_sql, parameters = self._filters(query, communication_result)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM job_postings {where_sql}", parameters
            ).fetchone()
        return int(row[0]) if row else 0

    def get(self, snapshot_id: int) -> StoredJob:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM job_postings WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return self._from_row(row)

    def create(self, job: CapturedJob) -> StoredJob:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO job_postings (
                    platform, platform_job_id, url, title, company_name, company_size,
                    location, work_address, salary_text, experience, education, description,
                    skills_json, recruiter_name, recruiter_title, captured_at,
                    has_communicated, has_interview, generated_greeting,
                    resume_variant, generated_resume_id, resume_optimization,
                    source, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.platform,
                    job.platform_job_id,
                    job.url,
                    job.title,
                    job.company_name,
                    job.company_size,
                    job.location,
                    job.work_address,
                    normalize_salary_text(job.salary_text),
                    job.experience,
                    job.education,
                    job.description,
                    json.dumps(job.skills, ensure_ascii=False),
                    job.recruiter_name,
                    job.recruiter_title,
                    job.captured_at.isoformat(),
                    int(job.has_communicated),
                    int(job.has_interview),
                    job.generated_greeting,
                    job.resume_variant,
                    job.generated_resume_id,
                    job.resume_optimization,
                    job.source,
                    self._content_hash(job),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
        return self.get(snapshot_id)

    def update_tracking(self, snapshot_id: int, data: dict[str, object]) -> StoredJob:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE job_postings SET
                    has_communicated = ?, has_interview = ?, generated_greeting = ?,
                    resume_variant = ?, generated_resume_id = ?, resume_optimization = ?
                WHERE id = ?""",
                (
                    int(bool(data["has_communicated"])),
                    int(bool(data["has_interview"])),
                    data.get("generated_greeting"),
                    data.get("resume_variant", "default"),
                    data.get("generated_resume_id"),
                    data.get("resume_optimization"),
                    snapshot_id,
                ),
            )
        if cursor.rowcount == 0:
            raise KeyError(snapshot_id)
        return self.get(snapshot_id)

    def update_generated_greeting(self, snapshot_id: int, greeting: str) -> StoredJob:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE job_postings SET generated_greeting = ? WHERE id = ?",
                (greeting, snapshot_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(snapshot_id)
        return self.get(snapshot_id)

    def list_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        query: str | None = None,
        communication_result: str | None = None,
    ) -> list[StoredJob]:
        self.initialize()
        where_sql, parameters = self._filters(query, communication_result)
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT * FROM job_postings {where_sql}
                ORDER BY captured_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _filters(
        query: str | None, communication_result: str | None
    ) -> tuple[str, tuple[object, ...]]:
        conditions: list[str] = []
        parameters: list[object] = []
        normalized = (query or "").strip().lower()
        if normalized:
            pattern = f"%{normalized}%"
            fields = (
                "title", "company_name", "company_size", "location", "work_address",
                "salary_text", "experience", "education", "description", "skills_json",
                "recruiter_name", "recruiter_title", "generated_greeting",
            )
            conditions.append(
                "(" + " OR ".join(
                    f"LOWER(COALESCE({field}, '')) LIKE ?" for field in fields
                ) + ")"
            )
            parameters.extend(pattern for _ in fields)

        result_filters = {
            "not_communicated": "has_communicated = 0",
            "communicated": "has_communicated = 1",
            "interviewed": "has_interview = 1",
        }
        if communication_result in result_filters:
            conditions.append(result_filters[communication_result])

        if not conditions:
            return "", ()
        return "WHERE " + " AND ".join(conditions), tuple(parameters)

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
    def _deduplicate_existing(connection: sqlite3.Connection) -> None:
        """Collapse legacy content versions into the newest stable job snapshot."""
        connection.execute(
            """UPDATE job_postings AS current SET
                has_communicated = (
                    SELECT MAX(other.has_communicated) FROM job_postings AS other
                    WHERE other.platform = current.platform
                      AND other.platform_job_id = current.platform_job_id
                ),
                has_interview = (
                    SELECT MAX(other.has_interview) FROM job_postings AS other
                    WHERE other.platform = current.platform
                      AND other.platform_job_id = current.platform_job_id
                ),
                generated_greeting = COALESCE(
                    current.generated_greeting,
                    (SELECT other.generated_greeting FROM job_postings AS other
                     WHERE other.platform = current.platform
                       AND other.platform_job_id = current.platform_job_id
                       AND other.generated_greeting IS NOT NULL
                     ORDER BY other.id DESC LIMIT 1)
                )"""
        )
        connection.execute(
            """DELETE FROM job_postings
            WHERE id NOT IN (
                SELECT MAX(id) FROM job_postings GROUP BY platform, platform_job_id
            )"""
        )

    @staticmethod
    def _content_hash(job: CapturedJob) -> str:
        content = "\n".join([job.title, job.company_name, job.description, "|".join(job.skills)])
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
            company_size=row["company_size"],
            location=row["location"],
            work_address=row["work_address"],
            salary_text=normalize_salary_text(row["salary_text"]),
            experience=row["experience"],
            education=row["education"],
            description=row["description"],
            skills=json.loads(row["skills_json"]),
            recruiter_name=row["recruiter_name"],
            recruiter_title=row["recruiter_title"],
            has_communicated=bool(row["has_communicated"]),
            has_interview=bool(row["has_interview"]),
            generated_greeting=row["generated_greeting"],
            resume_variant=row["resume_variant"],
            generated_resume_id=row["generated_resume_id"],
            resume_optimization=row["resume_optimization"],
            captured_at=row["captured_at"],
            source=row["source"],
            content_hash=row["content_hash"],
        )
