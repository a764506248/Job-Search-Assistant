"""Copy a SQLite database into PostgreSQL without modifying the source file.

Usage:
  python scripts/migrate_sqlite_to_postgres.py old.sqlite3 postgresql://...
"""

from __future__ import annotations

import argparse
import re
import sqlite3

import psycopg


def translate_ddl(sql: str) -> str:
    sql = re.sub(r"INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    sql = re.sub(r"\bBOOLEAN\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\s+COLLATE\s+NOCASE\b", "", sql, flags=re.I)
    return sql


def migrate(source: str, target: str) -> None:
    sqlite = sqlite3.connect(source)
    sqlite.row_factory = sqlite3.Row
    tables = [row[0] for row in sqlite.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    with psycopg.connect(target) as postgres:
        postgres.execute("SET session_replication_role = replica")
        indexes: list[str] = []
        for table in tables:
            ddl = sqlite.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()[0]
            postgres.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            postgres.execute(translate_ddl(ddl))
            indexes.extend(
                row[0] for row in sqlite.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
                    "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_autoindex_%'", (table,)
                )
            )
        for table in tables:
            columns = [row[1] for row in sqlite.execute(f'PRAGMA table_info("{table}")')]
            quoted = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            rows = sqlite.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
            if rows:
                postgres.cursor().executemany(
                    f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
                    [tuple(row) for row in rows],
                )
        for index_sql in indexes:
            postgres.execute(translate_ddl(index_sql))
        # BIGSERIAL sequences are not advanced by explicit id inserts.
        for table in tables:
            columns = [row[1] for row in sqlite.execute(f'PRAGMA table_info("{table}")')]
            if "id" in columns:
                postgres.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM \"" + table + "\"), 1), true)",
                    (table,),
                )
        postgres.execute("SET session_replication_role = DEFAULT")
    sqlite.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    migrate(args.source, args.target)
