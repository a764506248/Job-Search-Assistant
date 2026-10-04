from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .config import settings


class CompatRow:
    def __init__(self, columns: list[str], values: tuple[Any, ...]) -> None:
        self._columns = columns
        self._values = values
        self._index = {name: index for index, name in enumerate(columns)}

    def __getitem__(self, key: int | str) -> Any:
        return self._values[key] if isinstance(key, int) else self._values[self._index[key]]

    def __iter__(self):
        return iter(self._values)


class PostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid: int | None = None

    def fetchone(self) -> CompatRow | None:
        row = self._cursor.fetchone()
        return self._row(row)

    def fetchall(self) -> list[CompatRow]:
        return [self._row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        # A few legacy repository helpers iterate directly over sqlite cursors.
        # Keep that behavior for the PostgreSQL compatibility cursor.
        return iter(self.fetchall())

    def _row(self, row: Any) -> CompatRow | None:
        if row is None:
            return None
        columns = [column.name for column in self._cursor.description or []]
        return CompatRow(columns, tuple(row))


class PostgresConnection:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - deployment guard
            raise RuntimeError("使用 PostgreSQL 需要安装 psycopg[binary]") from error
        self._connection = psycopg.connect(dsn)
        self._row_factory_requested = False

    def __enter__(self) -> "PostgresConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._connection.__exit__(exc_type, exc, traceback)
        self.close()

    @property
    def row_factory(self) -> Any:
        return None

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._row_factory_requested = value is not None

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> PostgresCursor:
        pragma = re.fullmatch(r"\s*PRAGMA\s+table_info\((\w+)\)\s*", sql, re.I)
        if pragma:
            sql = """SELECT ordinal_position - 1 AS cid, column_name AS name,
                data_type AS type, CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
                column_default AS dflt_value, CASE WHEN column_name = 'id' THEN 1 ELSE 0 END AS pk
                FROM information_schema.columns WHERE table_schema = current_schema()
                AND table_name = %s ORDER BY ordinal_position"""
            parameters = (pragma.group(1),)
        elif sql.strip().lower() == "pragma optimize":
            sql = "SELECT 1"
        sql = _translate_sql(sql)
        cursor = self._connection.cursor()
        cursor.execute(sql, parameters)
        wrapped = PostgresCursor(cursor)
        if sql.lstrip().upper().startswith("INSERT"):
            if "RETURNING" in sql.upper():
                returned = cursor.fetchone()
                if returned:
                    wrapped.lastrowid = int(returned[0])
            else:
                # SQLite exposes lastrowid for every INSERT, while PostgreSQL
                # only has LASTVAL after a sequence-backed insert. Session and
                # join-table inserts do not need an id, so tolerate the absence.
                try:
                    cursor.execute("SELECT LASTVAL()")
                    wrapped.lastrowid = int(cursor.fetchone()[0])
                except Exception:
                    wrapped.lastrowid = None
        return wrapped

    def executescript(self, sql: str) -> None:
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        if not self._connection.closed:
            self._connection.close()


def db_connect(database_path: Path | str) -> Any:
    database_url = getattr(settings, "database_url", None)
    if database_url:
        return PostgresConnection(database_url)
    return sqlite3.connect(database_path)


def _translate_sql(sql: str) -> str:
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = sql.replace("?", "%s")
    return sql
