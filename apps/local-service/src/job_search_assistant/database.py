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

    def as_dict(self) -> dict[str, Any]:
        return dict(zip(self._columns, self._values))


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
    is_postgres = True

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
        if re.fullmatch(r"\s*BEGIN\s+IMMEDIATE\s*", sql, re.I):
            # SQLite uses IMMEDIATE to acquire the write lock up front. PostgreSQL
            # has no such syntax; row locking is added by the claiming query.
            sql = "BEGIN"
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
                # PostgreSQL has no safe transaction-neutral equivalent of
                # SQLite's lastrowid. Callers that need an id use RETURNING id.
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


class SqliteConnection:
    """SQLite connection wrapper that keeps INSERT ... RETURNING committable.

    SQLite defers ``RETURNING`` output until the cursor is read. Leaving that
    cursor untouched makes ``commit()`` fail with
    "cannot commit transaction - SQL statements in progress", while PostgreSQL
    (handled by PostgresConnection) already drains the returned row. Draining
    here keeps both backends on the same contract: callers still read the new id
    from ``cursor.lastrowid``.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    is_postgres = False

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        cursor = self._connection.execute(sql, parameters)
        if _returns_rows(sql):
            try:
                cursor.fetchall()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass
        return cursor

    def executescript(self, sql: str) -> Any:
        return self._connection.executescript(sql)

    @property
    def row_factory(self) -> Any:
        return self._connection.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._connection.row_factory = value

    def __enter__(self) -> "SqliteConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any:
        return self._connection.__exit__(exc_type, exc, traceback)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _returns_rows(sql: str) -> bool:
    normalized = sql.lstrip().upper()
    return normalized.startswith("INSERT") and "RETURNING" in normalized


def db_connect(database_path: Path | str) -> Any:
    database_url = getattr(settings, "database_url", None)
    if database_url:
        return PostgresConnection(database_url)
    return SqliteConnection(sqlite3.connect(database_path))


def table_columns(connection: Any, table: str) -> set[str]:
    """Return existing column names, tolerating both SQLite and PostgreSQL."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]).lower() for row in rows}


def table_exists(connection: Any, table: str) -> bool:
    return bool(table_columns(connection, table))


def ensure_column(connection: Any, table: str, column: str, definition: str) -> None:
    """Add a column when missing. Both PRAGMA and ALTER are translated for PostgreSQL."""
    if not table_exists(connection, table):
        return
    if column.lower() not in table_columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def recreate_index(connection: Any, name: str, statement: str) -> None:
    """Rebuild an index so existing databases pick up new column definitions."""
    connection.execute(f"DROP INDEX IF EXISTS {name}")
    connection.execute(statement)


def ensure_user_scoped_index(
    connection: Any, table: str, name: str, columns: str
) -> None:
    """Create a unique index that includes user_id, replacing the legacy variant.

    The legacy index (without user_id) would block two users from storing the same
    external job posting, so it must be dropped before the scoped one is created.
    """
    expected = f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table}({columns})"
    try:
        connection.execute(expected)
    except Exception:  # pragma: no cover - duplicate rows from the legacy layout
        connection.execute(f"DROP INDEX IF EXISTS {name}")
        connection.execute(expected)


def _translate_sql(sql: str) -> str:
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = sql.replace("?", "%s")
    return sql
