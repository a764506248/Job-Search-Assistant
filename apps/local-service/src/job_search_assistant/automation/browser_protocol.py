import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

PROTOCOL_VERSION = "1.0"
ALLOWED_ACTIONS = frozenset(
    {
        "ping",
        "session_status",
        "navigate_search",
        "capture_job",
        "collect_jobs",
        "open_job",
        "open_chat",
        "validate_identity",
        "send_greeting",
        "preview_resume",
        "send_resume",
    }
)


class BrowserProtocolError(RuntimeError):
    pass


@dataclass
class _Pairing:
    code_hash: str
    expires_at: datetime


@dataclass
class _Connection:
    websocket: WebSocket
    extension_version: str
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class BrowserConnectionHub:
    """User-scoped pairing and request/response broker for browser extensions."""

    def __init__(self, token_hash_path: Path | None = None) -> None:
        self._token_hash_path = token_hash_path
        self._pairings: dict[int | None, _Pairing] = {}
        self._token_hashes, self._legacy_token_hash = self._load_token_state()
        self._connections: dict[int, _Connection] = {}
        self._pending: dict[str, tuple[int, asyncio.Future[dict[str, Any]]]] = {}

    def create_pairing(self, user_id: int | None = None) -> dict[str, Any]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        self._pairings[user_id] = _Pairing(self._hash(code), expires_at)
        return {"code": code, "expiresAt": expires_at, "protocolVersion": PROTOCOL_VERSION}

    def exchange_pairing_code(self, code: str) -> str:
        supplied_hash = self._hash(code)
        matched = False
        owner_id: int | None = None
        for candidate_user_id, pairing in tuple(self._pairings.items()):
            if datetime.now(UTC) >= pairing.expires_at:
                self._pairings.pop(candidate_user_id, None)
                continue
            if secrets.compare_digest(pairing.code_hash, supplied_hash):
                owner_id = candidate_user_id
                matched = True
                break
        if not matched:
            raise BrowserProtocolError("invalid or expired pairing code")

        token = secrets.token_urlsafe(32)
        token_hash = self._hash(token)
        if owner_id is None:
            self._legacy_token_hash = token_hash
        else:
            self._token_hashes[owner_id] = token_hash
        self._persist_token_hashes()
        self._pairings.pop(owner_id, None)
        return token

    def authenticate(self, token: str) -> bool:
        if not token:
            return False
        token_hash = self._hash(token)
        return any(
            secrets.compare_digest(stored, token_hash) for stored in self._all_token_hashes()
        )

    def resolve_user(self, token: str) -> int | None:
        if not token:
            return None
        token_hash = self._hash(token)
        for user_id, stored_hash in self._token_hashes.items():
            if secrets.compare_digest(stored_hash, token_hash):
                return user_id
        return None

    def attach(self, websocket: WebSocket, extension_version: str, user_id: int) -> None:
        previous = self._connections.get(user_id)
        self._connections[user_id] = _Connection(websocket, extension_version)
        if previous is not None and previous.websocket is not websocket:
            self._fail_pending(user_id, "browser extension connection was replaced")

    def detach(self, websocket: WebSocket) -> None:
        owner_id = next(
            (
                user_id
                for user_id, connection in self._connections.items()
                if connection.websocket is websocket
            ),
            None,
        )
        if owner_id is None:
            return
        self._connections.pop(owner_id, None)
        self._fail_pending(owner_id, "browser extension disconnected")

    def status(self, user_id: int) -> dict[str, Any]:
        connection = self._connections.get(user_id)
        return {
            "connected": connection is not None,
            "paired": user_id in self._token_hashes,
            "protocolVersion": PROTOCOL_VERSION,
            "extensionVersion": connection.extension_version if connection else None,
        }

    def connected_user_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._connections))

    def connected_user_id(self) -> int | None:
        """Compatibility helper for callers that expect at most one connection."""
        connected = self.connected_user_ids()
        return connected[0] if len(connected) == 1 else None

    async def dispatch(
        self,
        *,
        run_id: int,
        user_id: int,
        action: str,
        payload: dict[str, Any],
        deadline_ms: int = 20_000,
    ) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise BrowserProtocolError(f"unsupported browser action: {action}")
        connection = self._connections.get(user_id)
        if connection is None:
            raise BrowserProtocolError("browser extension is not connected for this user")
        request_id = str(uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (user_id, future)
        envelope = {
            "requestId": request_id,
            "runId": run_id,
            "action": action,
            "deadlineMs": deadline_ms,
            "payload": payload,
        }
        try:
            async with connection.send_lock:
                await connection.websocket.send_json(envelope)
            return await asyncio.wait_for(future, timeout=deadline_ms / 1000)
        except TimeoutError as error:
            raise BrowserProtocolError(f"browser action timed out: {action}") from error
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, response: dict[str, Any], user_id: int | None = None) -> None:
        pending = self._pending.get(str(response.get("requestId", "")))
        if pending is None:
            return
        owner_id, future = pending
        if user_id is not None and owner_id != user_id:
            return
        if not future.done():
            future.set_result(response)

    def _fail_pending(self, user_id: int, message: str) -> None:
        for request_id, (owner_id, future) in tuple(self._pending.items()):
            if owner_id != user_id:
                continue
            if not future.done():
                future.set_exception(BrowserProtocolError(message))
            self._pending.pop(request_id, None)

    def _all_token_hashes(self) -> tuple[str, ...]:
        hashes = list(self._token_hashes.values())
        if self._legacy_token_hash:
            hashes.append(self._legacy_token_hash)
        return tuple(hashes)

    def _load_token_hash(self) -> str | None:
        hashes = self._all_token_hashes()
        return hashes[0] if hashes else None

    def _load_token_state(self) -> tuple[dict[int, str], str | None]:
        if self._token_hash_path is None or not self._token_hash_path.is_file():
            return {}, None
        raw = self._token_hash_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}, None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ({}, raw) if len(raw) == 64 else ({}, None)

        tokens: dict[int, str] = {}
        raw_tokens = data.get("tokens", {}) if isinstance(data, dict) else {}
        if isinstance(raw_tokens, dict):
            for raw_user_id, raw_hash in raw_tokens.items():
                try:
                    user_id = int(raw_user_id)
                except (TypeError, ValueError):
                    continue
                token_hash = str(raw_hash)
                if user_id > 0 and len(token_hash) == 64:
                    tokens[user_id] = token_hash

        legacy_hash = str(data.get("tokenHash", "")) if isinstance(data, dict) else ""
        if not legacy_hash and isinstance(data, dict):
            legacy_hash = str(data.get("legacyTokenHash", ""))
        raw_user_id = data.get("userId") if isinstance(data, dict) else None
        if len(legacy_hash) == 64:
            try:
                legacy_user_id = int(raw_user_id) if raw_user_id is not None else None
            except (TypeError, ValueError):
                legacy_user_id = None
            if legacy_user_id is not None and legacy_user_id > 0:
                tokens[legacy_user_id] = legacy_hash
                legacy_hash = ""
        return tokens, legacy_hash or None

    def _persist_token_hashes(self) -> None:
        if self._token_hash_path is None:
            return
        self._token_hash_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 2,
            "tokens": {
                str(user_id): token_hash for user_id, token_hash in self._token_hashes.items()
            },
        }
        if self._legacy_token_hash:
            payload["legacyTokenHash"] = self._legacy_token_hash
        temporary = self._token_hash_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self._token_hash_path)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
