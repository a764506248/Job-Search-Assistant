"""Print the Base URL embedded in a v2 Agent Key without printing the secret."""

from __future__ import annotations

import base64
import os
import re
import sys
from urllib.parse import urlsplit

KEY_PATTERN = re.compile(
    r"^jsa_agent_v2_([A-Za-z0-9_-]+)_([0-9a-f]{12})_([A-Za-z0-9_-]{43})$"
)


def resolve_base_url(key: str) -> str:
    match = KEY_PATTERN.fullmatch(key.strip())
    if match is None:
        raise ValueError("Key 未包含可识别的服务地址；旧版 Key 需要用户另行提供 Base URL")
    encoded = match.group(1)
    try:
        padding = "=" * (-len(encoded) % 4)
        base_url = base64.b64decode(encoded + padding, altchars=b"-_", validate=True).decode()
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Key 中的服务地址无效")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Key 中的服务地址端口无效")
    except (UnicodeError, ValueError) as error:
        raise ValueError("Key 中的服务地址无效") from error
    return base_url


def main() -> int:
    key = os.environ.get("JSA_AGENT_KEY", "").strip()
    if not key and not sys.stdin.isatty():
        key = sys.stdin.readline().strip()
    try:
        print(resolve_base_url(key))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
