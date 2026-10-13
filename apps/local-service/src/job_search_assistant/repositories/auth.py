from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..database import db_connect


class AuthRepository:
    """Account/session storage shared by the HTTP API and future user scopes."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with db_connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                """
            )

    def has_users(self) -> bool:
        self.initialize()
        with db_connect(self.database_path) as connection:
            return connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(self, username: str, password: str, *, is_admin: bool = False) -> dict:
        self.initialize()
        # Store usernames in a canonical form so SQLite and PostgreSQL enforce
        # the same case-insensitive account semantics.
        username = username.strip().lower()
        if len(username) < 3 or len(username) > 80:
            raise ValueError("用户名长度必须为 3-80 个字符")
        if len(password) < 8:
            raise ValueError("密码至少需要 8 个字符")
        now = datetime.now(UTC).isoformat()
        try:
            with db_connect(self.database_path) as connection:
                cursor = connection.execute(
                    """INSERT INTO users(username, password_hash, is_admin, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?) RETURNING id""",
                    (username, _hash_password(password), int(is_admin), now, now),
                )
                user_id = int(cursor.lastrowid)
        except Exception as error:
            if isinstance(error, sqlite3.IntegrityError) or "unique" in str(error).lower():
                raise ValueError("用户名已存在") from error
            raise
        return self.get_user(user_id)

    def authenticate(self, username: str, password: str) -> tuple[dict, str] | None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username.strip().lower(),),
            ).fetchone()
        if row is None or not _verify_password(password, row["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with db_connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (_token_hash(token), row["id"], (now + timedelta(days=30)).isoformat(), now.isoformat()),
            )
        return self._user(row), token

    def get_user_by_token(self, token: str) -> dict | None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1""",
                (_token_hash(token), datetime.now(UTC).isoformat()),
            ).fetchone()
        return self._user(row) if row is not None else None

    def delete_session(self, token: str) -> None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    def list_users(self) -> list[dict]:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [self._user(row) for row in rows]

    def get_user(self, user_id: int) -> dict:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise KeyError(user_id)
        return self._user(row)

    def update_user(self, user_id: int, *, password: str | None = None, is_admin: bool | None = None, is_active: bool | None = None) -> dict:
        self.initialize()
        fields: list[str] = []
        values: list[object] = []
        if password is not None:
            if len(password) < 8:
                raise ValueError("密码至少需要 8 个字符")
            fields.append("password_hash = ?"); values.append(_hash_password(password))
        if is_admin is not None:
            fields.append("is_admin = ?"); values.append(int(is_admin))
        if is_active is not None:
            fields.append("is_active = ?"); values.append(int(is_active))
        if fields:
            fields.append("updated_at = ?"); values.append(datetime.now(UTC).isoformat()); values.append(user_id)
            with db_connect(self.database_path) as connection:
                connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", tuple(values))
        return self.get_user(user_id)

    def delete_user(self, user_id: int) -> None:
        self.initialize()
        with db_connect(self.database_path) as connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))

    @staticmethod
    def _user(row: sqlite3.Row) -> dict:
        return {"id": int(row["id"]), "username": row["username"], "isAdmin": bool(row["is_admin"]), "isActive": bool(row["is_active"]), "createdAt": row["created_at"]}


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
