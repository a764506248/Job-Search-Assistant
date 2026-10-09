import asyncio
import hashlib
import json
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
        self._pairing_user_id: int | None = None
        state = self._load_token_state()
        self._token_hash: str | None = state[0] if state else None
        self._token_user_id: int | None = state[1] if state else None
        self._websocket: WebSocket | None = None
        self._websocket_user_id: int | None = None
        self._extension_version: str | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._send_lock = asyncio.Lock()

    def create_pairing(self, user_id: int | None = None) -> dict[str, Any]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        self._pairing_hash = self._hash(code)
        self._pairing_expires_at = expires_at
        # 配对码由某个登录用户生成，扩展后续采集的数据就归属该用户。
        self._pairing_user_id = user_id
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
        self._token_user_id = self._pairing_user_id
        self._persist_token_hash(self._token_hash, self._token_user_id)
        self._pairing_hash = None
        self._pairing_expires_at = None
        self._pairing_user_id = None
        return token

    def authenticate(self, token: str) -> bool:
        return bool(
            self._token_hash
            and secrets.compare_digest(self._token_hash, self._hash(token))
        )

    def resolve_user(self, token: str) -> int | None:
        """Map an extension token to the user that created its pairing code."""
        if not token or not self._token_hash:
            return None
        if not secrets.compare_digest(self._token_hash, self._hash(token)):
            return None
        return self._token_user_id

    def attach(self, websocket: WebSocket, extension_version: str, user_id: int) -> None:
        self._websocket = websocket
        self._websocket_user_id = user_id
        self._extension_version = extension_version

    def detach(self, websocket: WebSocket) -> None:
        if self._websocket is not websocket:
            return
        self._websocket = None
        self._websocket_user_id = None
        self._extension_version = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(BrowserProtocolError("browser extension disconnected"))
        self._pending.clear()

    def status(self, user_id: int) -> dict[str, Any]:
        owned_connection = self._websocket is not None and self._websocket_user_id == user_id
        return {
            "connected": owned_connection,
            "paired": self._token_hash is not None and self._token_user_id == user_id,
            "protocolVersion": PROTOCOL_VERSION,
            "extensionVersion": self._extension_version if owned_connection else None,
        }

    def connected_user_id(self) -> int | None:
        """Return the owner of the currently attached browser extension."""
        return self._websocket_user_id if self._websocket is not None else None

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
        websocket = self._websocket
        if websocket is None:
            raise BrowserProtocolError("browser extension is not connected")
        if self._websocket_user_id != user_id:
            raise BrowserProtocolError(
                "browser extension belongs to a different user; pair this account before continuing"
            )
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
        state = self._load_token_state()
        return state[0] if state else None

    def _load_token_state(self) -> tuple[str, int | None] | None:
        """Read the persisted pairing token together with its owning user.

        Legacy files contain the bare token hash; those are treated as belonging
        to the first local account so existing pairings keep working.
        """
        if self._token_hash_path is None or not self._token_hash_path.is_file():
            return None
        raw = self._token_hash_path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return (raw, None) if len(raw) == 64 else None
        token_hash = str(data.get("tokenHash", ""))
        if len(token_hash) != 64:
            return None
        raw_user_id = data.get("userId")
        try:
            user_id = int(raw_user_id) if raw_user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        return token_hash, user_id

    def _persist_token_hash(self, token_hash: str, user_id: int | None = None) -> None:
        if self._token_hash_path is None:
            return
        self._token_hash_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"tokenHash": token_hash, "userId": user_id}, ensure_ascii=False)
        temporary = self._token_hash_path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self._token_hash_path)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
