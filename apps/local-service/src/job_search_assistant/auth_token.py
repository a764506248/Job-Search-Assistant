import base64
import hashlib
import hmac
import json
import time

from .config import settings

def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

def issue_token(user: dict, ttl_seconds: int = 30 * 86400) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": str(user["id"]), "username": user["username"], "isAdmin": bool(user["isAdmin"]), "exp": int(time.time()) + ttl_seconds}, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    return f"{header}.{payload}.{_b64(hmac.new(_secret(), signing, hashlib.sha256).digest())}"

def verify_token(token: str) -> dict | None:
    try:
        header, payload, signature = token.split(".")
        signing = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(_secret(), signing, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data.get("exp", 0)) <= int(time.time()): return None
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

def _secret() -> bytes:
    return (settings.jwt_secret or "development-only-change-me").encode()
