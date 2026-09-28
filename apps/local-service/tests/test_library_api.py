from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


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
