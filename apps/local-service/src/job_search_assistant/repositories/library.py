from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

LibraryKind = Literal["projects", "resumes", "rules", "models", "targets"]
ALLOWED_KINDS = {"projects", "resumes", "rules", "models", "targets"}


class LibraryRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS library_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_library_records_kind_updated
                ON library_records(kind, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("PRAGMA optimize")

    def list(self, kind: LibraryKind) -> list[dict[str, Any]]:
        self._validate_kind(kind)
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM library_records WHERE kind = ? ORDER BY updated_at DESC, id DESC",
                (kind,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def create(self, kind: LibraryKind, name: str, data: dict[str, Any]) -> dict[str, Any]:
        self._validate_kind(kind)
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO library_records(kind, name, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (kind, name, json.dumps(data, ensure_ascii=False), now, now),
            )
            record_id = cursor.lastrowid
            if kind == "models":
                self._make_model_role_exclusive(connection, int(record_id), data)
        return self.get(kind, int(record_id))

    def get(self, kind: LibraryKind, record_id: int) -> dict[str, Any]:
        self._validate_kind(kind)
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM library_records WHERE kind = ? AND id = ?",
                (kind, record_id),
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return self._row(row)

    def update(
        self, kind: LibraryKind, record_id: int, name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        self._validate_kind(kind)
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE library_records SET name = ?, data_json = ?, updated_at = ?
                WHERE kind = ? AND id = ?
                """,
                (
                    name,
                    json.dumps(data, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                    kind,
                    record_id,
                ),
            )
            if kind == "models" and cursor.rowcount:
                self._make_model_role_exclusive(connection, record_id, data)
        if cursor.rowcount == 0:
            raise KeyError(record_id)
        return self.get(kind, record_id)

    def delete(self, kind: LibraryKind, record_id: int) -> bool:
        self._validate_kind(kind)
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM library_records WHERE kind = ? AND id = ?",
                (kind, record_id),
            )
        return cursor.rowcount > 0

    def get_profile(self) -> dict[str, Any]:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT data_json FROM profile WHERE singleton = 1").fetchone()
        return self._structure_profile(json.loads(row[0])) if row else {}

    def save_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        data = self._structure_profile(data)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profile(singleton, data_json, updated_at) VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (json.dumps(data, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )
        return data

    def import_resume(
        self,
        filename: str,
        profile: dict[str, Any],
        resume: dict[str, Any],
        projects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data_json FROM profile WHERE singleton = 1"
            ).fetchone()
            current_profile = json.loads(row[0]) if row else {}
            merged_profile = self._structure_profile({**current_profile, **profile})
            connection.execute(
                """INSERT INTO profile(singleton, data_json, updated_at) VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at""",
                (json.dumps(merged_profile, ensure_ascii=False), now),
            )
            resume_cursor = connection.execute(
                """INSERT INTO library_records(kind, name, data_json, created_at, updated_at)
                VALUES ('resumes', ?, ?, ?, ?)""",
                (filename, json.dumps(resume, ensure_ascii=False), now, now),
            )
            project_ids = self._upsert_projects(connection, projects, now)
        return {
            "profile": merged_profile,
            "resumeId": resume_cursor.lastrowid,
            "projectIds": project_ids,
        }

    def upsert_projects(self, projects: list[dict[str, Any]]) -> list[int]:
        """Persist structured projects and return their stable entity IDs."""
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            return self._upsert_projects(connection, projects, now)

    @staticmethod
    def _upsert_projects(
        connection: sqlite3.Connection,
        projects: list[dict[str, Any]],
        now: str,
    ) -> list[int]:
        project_ids: list[int] = []
        existing_projects = connection.execute(
            "SELECT id, data_json FROM library_records WHERE kind = 'projects'"
        ).fetchall()
        projects_by_source_key = {
            data.get("sourceKey"): record_id
            for record_id, data_json in existing_projects
            if (data := json.loads(data_json)).get("sourceKey")
        }
        for project in projects:
            source_key = project["data"].get("sourceKey")
            existing_id = projects_by_source_key.get(source_key)
            if existing_id:
                connection.execute(
                    """UPDATE library_records SET name = ?, data_json = ?, updated_at = ?
                    WHERE kind = 'projects' AND id = ?""",
                    (
                        project["name"],
                        json.dumps(project["data"], ensure_ascii=False),
                        now,
                        existing_id,
                    ),
                )
                project_ids.append(existing_id)
            else:
                cursor = connection.execute(
                    """INSERT INTO library_records(kind, name, data_json, created_at, updated_at)
                    VALUES ('projects', ?, ?, ?, ?)""",
                    (
                        project["name"],
                        json.dumps(project["data"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                project_id = int(cursor.lastrowid)
                project_ids.append(project_id)
                if source_key:
                    projects_by_source_key[source_key] = project_id
        return project_ids

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _structure_profile(data: dict[str, Any]) -> dict[str, Any]:
        """Keep editable text fields while materializing stable entities for RAG."""
        structured = dict(data)
        summary = str(structured.get("summary", "")).strip()
        if summary and not structured.get("strengths"):
            strength_lines = LibraryRepository._until_heading(
                LibraryRepository._content_lines(summary),
                (r"^技术栈$", r"^项目经历$", r"^工作经历$", r"^教育经历$"),
            )
            structured["strengths"] = [
                {"id": f"strength-{index}", "content": line}
                for index, line in enumerate(strength_lines, 1)
            ]

        tech_stack = str(structured.get("techStack", "")).strip()
        if tech_stack and not structured.get("techStackGroups"):
            groups: list[dict[str, Any]] = []
            tech_lines = LibraryRepository._until_heading(
                LibraryRepository._content_lines(tech_stack),
                (
                    r"^(?:项目|项⽬).*(?:实践|经历)",
                    r"^工作经历$",
                    r"^教育经历$",
                    r"^早期工作与项目$",
                ),
            )
            for line in tech_lines:
                parts = re.split(r"[：:]", line, maxsplit=1)
                if len(parts) == 2:
                    name, values = parts
                    groups.append(
                        {
                            "id": f"tech-{len(groups) + 1}",
                            "name": name.strip(),
                            "items": LibraryRepository._items(values),
                        }
                    )
                elif groups:
                    groups[-1]["items"] = list(
                        dict.fromkeys([*groups[-1]["items"], *LibraryRepository._items(line)])
                    )
                else:
                    groups.append(
                        {
                            "id": "tech-1",
                            "name": "技术栈",
                            "items": LibraryRepository._items(line),
                        }
                    )
            structured["techStackGroups"] = groups

        for source_key, target_key, prefix in (
            ("workExperience", "workExperiences", "work"),
            ("education", "educations", "education"),
        ):
            value = str(structured.get(source_key, "")).strip()
            if value and not structured.get(target_key):
                structured[target_key] = [
                    {"id": f"{prefix}-1", "content": value}
                ]
        return structured

    @staticmethod
    def _make_model_role_exclusive(
        connection: sqlite3.Connection, record_id: int, data: dict[str, Any]
    ) -> None:
        role = str(data.get("usageRole", "available"))
        if role not in ("primary", "fallback"):
            return
        rows = connection.execute(
            "SELECT id, data_json FROM library_records WHERE kind = 'models' AND id != ?",
            (record_id,),
        ).fetchall()
        now = datetime.now(UTC).isoformat()
        for other_id, raw_data in rows:
            other = json.loads(raw_data)
            if other.get("usageRole") == role:
                other["usageRole"] = "available"
                connection.execute(
                    "UPDATE library_records SET data_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(other, ensure_ascii=False), now, other_id),
                )

    @staticmethod
    def _content_lines(value: str) -> list[str]:
        return [
            re.sub(r"^[•·▪◦*-]\s*", "", line).strip()
            for line in value.splitlines()
            if re.sub(r"^[•·▪◦*-]\s*", "", line).strip()
        ]

    @staticmethod
    def _until_heading(lines: list[str], heading_patterns: tuple[str, ...]) -> list[str]:
        for index, line in enumerate(lines):
            if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in heading_patterns):
                return lines[:index]
        return lines

    @staticmethod
    def _items(value: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"[,，、/|]", value)
            if item.strip()
        ]

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"unsupported library kind: {kind}")

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "name": row["name"],
            "data": json.loads(row["data_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
