from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


class FakeEmbedder:
    model = "test/bge-small-zh"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [
                float(text.count("Python") + text.count("后端")),
                float(text.count("Vue") + text.count("前端")),
                1.0,
            ]
            for text in texts
        ]


def test_rebuild_and_search_local_knowledge(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    client.put(
        "/v1/profile",
        json={"data": {"targetRoles": "Python 后端工程师", "summary": "熟悉 FastAPI"}},
    )
    client.post(
        "/v1/library/projects",
        json={
            "name": "企业知识库",
            "data": {"summary": "使用 Python 和 FastAPI 构建 RAG 服务", "tags": "Python,RAG"},
        },
    )
    client.post(
        "/v1/library/projects",
        json={"name": "管理后台", "data": {"summary": "使用 Vue 开发前端", "tags": "Vue"}},
    )

    rebuilt = client.post("/v1/rag/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["rebuilt"] == 3
    assert rebuilt.json()["model"] == "test/bge-small-zh"

    status = client.get("/v1/rag/status")
    assert status.status_code == 200
    assert status.json()["embeddingAvailable"] is True
    assert status.json()["sources"] == 3

    search = client.post("/v1/rag/search", json={"query": "Python 后端", "limit": 2})
    assert search.status_code == 200
    items = search.json()["items"]
    assert len(items) == 2
    assert items[0]["sourceName"] in {"个人档案", "企业知识库"}
    assert items[0]["score"] >= items[1]["score"]


class OfflineEmbedder(FakeEmbedder):
    def health(self) -> dict[str, object]:
        raise RuntimeError("offline")

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("offline")


def test_offline_embedding_service_is_reported(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=OfflineEmbedder()))

    status = client.get("/v1/rag/status")
    assert status.status_code == 200
    assert status.json()["embeddingAvailable"] is False

    rebuild = client.post("/v1/rag/rebuild")
    assert rebuild.status_code == 503
