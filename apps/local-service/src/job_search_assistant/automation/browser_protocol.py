import asyncio
import hashlib
import secrets
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


class BrowserConnectionHub:
    """In-memory localhost pairing and request/response broker for the extension."""

    def __init__(self, token_hash_path: Path | None = None) -> None:
        self._token_hash_path = token_hash_path
        self._pairing_hash: str | None = None
        self._pairing_expires_at: datetime | None = None
        self._token_hash: str | None = self._load_token_hash()
        self._websocket: WebSocket | None = None
        self._extension_version: str | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._send_lock = asyncio.Lock()

    def create_pairing(self) -> dict[str, Any]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        self._pairing_hash = self._hash(code)
        self._pairing_expires_at = expires_at
        return {"code": code, "expiresAt": expires_at, "protocolVersion": PROTOCOL_VERSION}

    def exchange_pairing_code(self, code: str) -> str:
        if (
            not self._pairing_hash
            or not self._pairing_expires_at
            or datetime.now(UTC) >= self._pairing_expires_at
            or not secrets.compare_digest(self._pairing_hash, self._hash(code))
        ):
            raise BrowserProtocolError("invalid or expired pairing code")
        token = secrets.token_urlsafe(32)
        self._token_hash = self._hash(token)
        self._persist_token_hash(self._token_hash)
        self._pairing_hash = None
        self._pairing_expires_at = None
        return token

    def authenticate(self, token: str) -> bool:
        return bool(
            self._token_hash
            and secrets.compare_digest(self._token_hash, self._hash(token))
        )

    def attach(self, websocket: WebSocket, extension_version: str) -> None:
        self._websocket = websocket
        self._extension_version = extension_version

    def detach(self, websocket: WebSocket) -> None:
        if self._websocket is websocket:
            self._websocket = None
            self._extension_version = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(BrowserProtocolError("browser extension disconnected"))
        self._pending.clear()

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._websocket is not None,
            "paired": self._token_hash is not None,
            "protocolVersion": PROTOCOL_VERSION,
            "extensionVersion": self._extension_version,
        }

    async def dispatch(
        self,
        *,
        run_id: int,
        action: str,
        payload: dict[str, Any],
        deadline_ms: int = 20_000,
    ) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise BrowserProtocolError(f"unsupported browser action: {action}")
        websocket = self._websocket
        if websocket is None:
            raise BrowserProtocolError("browser extension is not connected")
        request_id = str(uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        envelope = {
            "requestId": request_id,
            "runId": run_id,
            "action": action,
            "deadlineMs": deadline_ms,
            "payload": payload,
        }
        try:
            async with self._send_lock:
                await websocket.send_json(envelope)
            return await asyncio.wait_for(future, timeout=deadline_ms / 1000)
        except TimeoutError as error:
            raise BrowserProtocolError(f"browser action timed out: {action}") from error
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, response: dict[str, Any]) -> None:
        request_id = str(response.get("requestId", ""))
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(response)

    def _load_token_hash(self) -> str | None:
        if self._token_hash_path is None or not self._token_hash_path.is_file():
            return None
        value = self._token_hash_path.read_text(encoding="utf-8").strip()
        return value if len(value) == 64 else None

    def _persist_token_hash(self, token_hash: str) -> None:
        if self._token_hash_path is None:
            return
        self._token_hash_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._token_hash_path.with_suffix(".tmp")
        temporary.write_text(token_hash, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self._token_hash_path)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
