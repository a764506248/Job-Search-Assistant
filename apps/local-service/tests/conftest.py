"""共享测试基座。

用户数据隔离改造后，所有数据接口都要求登录身份。测试用例大多直接构造
``TestClient(create_app(...))``，这里统一在客户端首次请求之前准备好一个已登录
账号。

身份准备刻意绕开 HTTP 层：在 ``TestClient.request`` 内再发请求会让 SQLite 连接
停在未提交的事务里，抛 "cannot commit transaction - SQL statements in progress"。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from job_search_assistant.auth_token import issue_token
from job_search_assistant.repositories import AuthRepository

TEST_USERNAME = "tester"
TEST_PASSWORD = "password123"
MARKER = "_jsa_auto_login_done"


def authenticate(
    client: TestClient, username: str = TEST_USERNAME, password: str = TEST_PASSWORD
) -> None:
    """Prepare the account directly through the data layer and set the bearer token."""
    app = getattr(client, "app", None)
    database_path = getattr(getattr(app, "state", None), "database_path", None)
    if database_path is None:
        return
    repository = AuthRepository(database_path)
    repository.initialize()
    if not repository.has_users():
        repository.create_user(username, password, is_admin=True)
    result = repository.authenticate(username, password)
    if result is None:
        # 只让默认测试账号成为管理员，其余账号按普通用户创建，便于验证权限边界。
        repository.create_user(username, password, is_admin=username == TEST_USERNAME)
        result = repository.authenticate(username, password)
    if result is None:
        return
    user, _session = result
    client.headers["Authorization"] = f"Bearer {issue_token(user)}"


def _ensure_login(client: TestClient) -> None:
    if getattr(client, MARKER, False):
        return
    setattr(client, MARKER, True)
    app = getattr(client, "app", None)
    if app is not None and str(getattr(app, "title", "")).startswith("Job Search Assistant"):
        authenticate(client)


@pytest.fixture(autouse=True)
def _auto_authenticated_client(monkeypatch: pytest.MonkeyPatch) -> None:
    original_request = TestClient.request
    original_stream = TestClient.stream

    def patched_request(self: TestClient, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ensure_login(self)
        return original_request(self, *args, **kwargs)

    def patched_stream(self: TestClient, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ensure_login(self)
        return original_stream(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", patched_request)
    monkeypatch.setattr(TestClient, "stream", patched_stream)
