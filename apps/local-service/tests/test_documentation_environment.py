from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from job_search_assistant.config import Settings, settings
from job_search_assistant.main import create_app

DOCUMENTATION_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


def test_documentation_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JSA_ENV", raising=False)
    assert Settings(_env_file=None).env == "production"


def test_invalid_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSA_ENV", "prodution")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("environment", ["local", "production"])
@pytest.mark.parametrize("host", ["localhost", "jsazhushou.cn"])
def test_documentation_depends_on_environment_not_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment: str, host: str
) -> None:
    monkeypatch.setenv("JSA_ENV", environment)
    monkeypatch.setattr(settings, "env", Settings(_env_file=None).env)
    application = create_app(database_path=tmp_path / "jobs.sqlite3")
    with TestClient(application, base_url=f"http://{host}") as client:
        for path in DOCUMENTATION_PATHS:
            response = client.get(path)
            assert response.status_code == (200 if environment == "local" else 404), path
        if environment == "local":
            schema = client.get("/openapi.json").json()
            assert "/v1/agent/me" in schema["paths"]
            assert "/openapi.json" in client.get("/docs").text

        assert client.get("/v1/health").json()["status"] == "ok"
        # The shared fixture authenticates test clients; explicitly remove that
        # token to verify closing docs does not replace normal API authentication.
        client.headers.pop("Authorization", None)
        assert client.get("/v1/profile").status_code == 401
        assert client.get("/v1/agent/me").status_code == 401
