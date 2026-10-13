"""多用户数据隔离与鉴权的专项测试。

覆盖：未登录拒绝、跨用户读写互不可见、越权任务访问、管理员权限、首次启动引导、
以及浏览器扩展令牌的账号归属。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import MARKER, authenticate
from job_search_assistant.automation.browser_protocol import BrowserConnectionHub
from job_search_assistant.config import settings
from job_search_assistant.main import create_app
from job_search_assistant.repositories import AuthRepository

OTHER_USER = "second-user"
OTHER_PASSWORD = "password123"

PROTECTED_GET_PATHS = (
    "/v1/auth/me",
    "/v1/jobs",
    "/v1/profile",
    "/v1/library/projects",
    "/v1/library/resumes",
    "/v1/library/rules",
    "/v1/library/models",
    "/v1/deliveries",
    "/v1/client-logs",
    "/v1/automation/runs",
    "/v1/automation/config",
    "/v1/setup/status",
    "/v1/browser/status",
    "/v1/admin/users",
)


def test_protected_endpoints_require_login(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    # 跳过 conftest 的自动登录，模拟未登录调用方。
    setattr(client, MARKER, True)
    client.headers.pop("Authorization", None)

    for path in PROTECTED_GET_PATHS:
        assert client.get(path).status_code == 401, path


def test_public_endpoints_stay_open(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    setattr(client, MARKER, True)
    client.headers.pop("Authorization", None)

    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/auth/bootstrap").status_code == 200
    assert client.get("/v1/resume-templates").status_code == 200


def test_profile_and_library_are_isolated_per_user(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    assert client.put("/v1/profile", json={"data": {"displayName": "第一个用户"}}).status_code == 200
    created = client.post(
        "/v1/library/projects", json={"name": "只属于第一个用户", "data": {"summary": "私有"}}
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert client.get("/v1/profile").json()["data"]["displayName"] == "第一个用户"

    # 切换到第二个账号：看不到档案，也拿不到别人的项目记录。
    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    assert client.get("/v1/profile").json()["data"] == {}
    assert client.get("/v1/library/projects").json()["items"] == []
    assert client.get(f"/v1/library/projects/{project_id}").status_code in (404, 405)
    assert client.put(
        f"/v1/library/projects/{project_id}", json={"name": "改名", "data": {}}
    ).status_code == 404
    assert client.delete(f"/v1/library/projects/{project_id}").status_code == 404


def test_job_snapshots_are_isolated_per_user(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    job = {
        "platform": "boss",
        "platformJobId": "isolation-job",
        "url": "https://www.zhipin.com/job_detail/isolation-job.html",
        "title": "AI Agent 工程师",
        "companyName": "示例公司",
        "description": "负责 RAG 与 Agent 应用开发",
        "skills": ["Python"],
        "capturedAt": "2026-10-04T08:00:00Z",
        "source": "manual",
    }
    assert client.post("/v1/jobs", json=job).status_code == 201
    first = client.get("/v1/jobs").json()
    assert first["total"] == 1
    snapshot_id = first["items"][0]["id"]

    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    second = client.get("/v1/jobs").json()
    assert second["total"] == 0
    assert client.put(
        f"/v1/jobs/{snapshot_id}/tracking",
        json={"hasCommunicated": True, "hasInterview": False},
    ).status_code == 404
    assert client.delete(f"/v1/jobs/{snapshot_id}").status_code == 404

    # 第二个用户可以保存同一个外部职位，不会被唯一索引挡住。
    assert client.post("/v1/jobs", json=job).status_code == 201
    assert client.get("/v1/jobs").json()["total"] == 1


def test_extension_logs_are_isolated_per_user(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "source": "extension-content",
        "level": "error",
        "event": "collection-failed",
        "message": "只属于第一个用户",
        "details": {},
        "occurredAt": "2026-10-07T08:00:00Z",
    }
    assert client.post("/v1/client-logs", json=payload).status_code == 201
    assert len(client.get("/v1/client-logs").json()["items"]) == 1

    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    assert client.get("/v1/client-logs").json()["items"] == []


def test_automation_run_is_scoped_to_its_owner(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    created = client.post(
        "/v1/automation/runs", json={"targetCount": 1, "config": {"plannedJobs": []}}
    ).json()
    run_id = created["id"]

    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    assert client.get(f"/v1/automation/runs/{run_id}").status_code == 404
    assert client.get(f"/v1/automation/runs/{run_id}/report").status_code == 404
    assert client.get(f"/v1/automation/runs/{run_id}/events").status_code == 404
    assert client.post(f"/v1/automation/runs/{run_id}/collect").status_code == 404
    assert client.post(f"/v1/automation/runs/{run_id}/start").status_code == 404
    assert client.get("/v1/automation/runs").json()["items"] == []


def test_admin_endpoints_require_admin_role(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    # conftest 创建的首个账号是管理员。
    assert client.get("/v1/admin/users").status_code == 200

    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    assert client.get("/v1/admin/users").status_code == 403
    assert client.post(
        "/v1/admin/users", json={"username": "third-user", "password": "password123"}
    ).status_code == 403


def test_disabled_user_existing_jwt_is_rejected(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    setattr(client, MARKER, True)
    authenticate(client, OTHER_USER, OTHER_PASSWORD)
    repository = AuthRepository(client.app.state.database_path)
    user = next(item for item in repository.list_users() if item["username"] == OTHER_USER)
    repository.update_user(int(user["id"]), is_active=False)

    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/jobs").status_code == 401


def test_current_admin_cannot_remove_own_admin_role(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    current = client.get("/v1/auth/me").json()["user"]

    response = client.patch(
        f"/v1/admin/users/{current['id']}", json={"isAdmin": False}
    )
    assert response.status_code == 400


def test_bootstrap_guides_first_admin_and_closes_self_service(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    # 跳过 conftest 的自动建号，模拟全新部署的空数据库。
    setattr(client, MARKER, True)

    assert client.get("/v1/auth/bootstrap").json() == {"needsSetup": True}

    registered = client.post(
        "/v1/auth/register", json={"username": "first-admin", "password": "password123"}
    )
    assert registered.status_code == 200
    assert registered.json()["user"]["isAdmin"] is True
    assert client.get("/v1/auth/bootstrap").json() == {"needsSetup": False}

    # 初始化完成后自助注册关闭。
    assert client.post(
        "/v1/auth/register", json={"username": "self-service", "password": "password123"}
    ).status_code == 403


def test_extension_token_belongs_to_pairing_account(tmp_path) -> None:
    hub = BrowserConnectionHub()
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", browser_hub=hub))

    # 登录用户在后台生成配对码，扩展用它换取本地令牌。
    pairing = client.post("/v1/browser/pairing").json()
    token = hub.exchange_pairing_code(pairing["code"])
    assert hub.resolve_user(token) == 1

    # 扩展只带本地令牌（没有 JWT）时，身份仍解析为配对账号。
    client.headers.pop("Authorization", None)
    assert client.get("/v1/auth/me", headers={"X-Local-Token": token}).json()["user"][
        "username"
    ] == "tester"
    assert client.get("/v1/jobs", headers={"X-Local-Token": token}).status_code == 200
    # 无效令牌不会放行。
    assert client.get("/v1/jobs", headers={"X-Local-Token": "not-a-token"}).status_code == 401


def test_pairing_requires_login(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    setattr(client, MARKER, True)
    client.headers.pop("Authorization", None)
    assert client.post("/v1/browser/pairing").status_code == 401


def test_runner_endpoints_require_runner_token_when_configured(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "runner_token", "runner-test-secret")
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    assert client.post(
        "/v1/automation/runner/heartbeat", json={"runnerId": "test-runner"}
    ).status_code == 401
    assert client.post(
        "/v1/automation/runner/heartbeat",
        json={"runnerId": "test-runner"},
        headers={"X-Runner-Token": "runner-test-secret"},
    ).status_code == 200
