from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


class FakeModelTester:
    def test(self, config: dict[str, object]) -> dict[str, object]:
        assert config["apiKey"] == "sk-local-secret"
        return {
            "ok": True,
            "provider": config["provider"],
            "modelId": config["modelId"],
            "latencyMs": 12,
            "message": "连接成功，模型已返回内容",
        }


def test_profile_and_library_crud(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "assistant.sqlite3"))

    profile = client.put(
        "/v1/profile",
        json={"data": {"displayName": "测试用户", "targetRoles": "AI应用开发"}},
    )
    assert profile.status_code == 200
    assert client.get("/v1/profile").json()["data"]["displayName"] == "测试用户"

    created = client.post(
        "/v1/library/projects",
        json={
            "name": "知识库项目",
            "data": {"repositoryUrl": "https://github.com/example/repo", "tags": "RAG,Python"},
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]
    assert client.get("/v1/library/projects").json()["items"][0]["name"] == "知识库项目"

    updated = client.put(
        f"/v1/library/projects/{record_id}",
        json={"name": "RAG知识库", "data": {"tags": "RAG,FastAPI"}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "RAG知识库"

    deleted = client.delete(f"/v1/library/projects/{record_id}")
    assert deleted.status_code == 204
    assert client.get("/v1/library/projects").json()["items"] == []


def test_unknown_library_kind_is_rejected(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "assistant.sqlite3"))

    assert client.get("/v1/library/unknown").status_code == 404


def test_model_configuration_requires_credentials_and_masks_api_key(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "assistant.sqlite3", model_tester=FakeModelTester())
    )

    invalid = client.post(
        "/v1/library/models",
        json={"name": "主模型", "data": {"modelId": "gpt-test"}},
    )
    assert invalid.status_code == 422

    created = client.post(
        "/v1/library/models",
        json={
            "name": "主模型",
            "data": {
                "provider": "OpenAI Compatible",
                "modelId": "gpt-test",
                "apiKey": "sk-local-secret",
                "baseUrl": "https://api.example.com/v1",
            },
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]
    assert "apiKey" not in created.json()["data"]
    assert created.json()["data"]["apiKeyConfigured"] is True
    assert created.json()["data"]["apiKeyHint"] == "••••cret"

    listing = client.get("/v1/library/models").json()["items"]
    assert "apiKey" not in listing[0]["data"]

    updated = client.put(
        f"/v1/library/models/{record_id}",
        json={
            "name": "主模型",
            "data": {
                "provider": "OpenAI Compatible",
                "modelId": "gpt-test-2",
                "baseUrl": "https://api.example.com/v1",
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["modelId"] == "gpt-test-2"
    assert updated.json()["data"]["apiKeyHint"] == "••••cret"

    connection = client.post(f"/v1/library/models/{record_id}/test")
    assert connection.status_code == 200
    assert connection.json() == {
        "ok": True,
        "provider": "OpenAI Compatible",
        "modelId": "gpt-test-2",
        "latencyMs": 12,
        "message": "连接成功，模型已返回内容",
    }
