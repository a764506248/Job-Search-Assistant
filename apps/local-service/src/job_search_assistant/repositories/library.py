import json
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
        return json.loads(row[0]) if row else {}

    def save_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

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
