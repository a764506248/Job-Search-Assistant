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
    project_response = client.post(
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
    client.post(
        "/v1/library/resumes",
        json={"name": "原始简历", "data": {"rawText": "这段原始简历不能被机械切片"}},
    )

    rebuilt = client.post("/v1/rag/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["rebuilt"] == 3
    assert rebuilt.json()["model"] == "test/bge-small-zh"

    status = client.get("/v1/rag/status")
    assert status.status_code == 200
    assert status.json()["embeddingAvailable"] is True
    assert status.json()["sources"] == 3

    chunks = client.get("/v1/rag/chunks")
    assert chunks.status_code == 200
    chunk_data = chunks.json()
    assert chunk_data["total"] == 3
    assert len(chunk_data["items"]) == 3
    assert chunk_data["items"][0]["dimensions"] == 3
    assert len(chunk_data["items"][0]["embedding"]) == 3
    assert chunk_data["items"][0]["contentHash"]
    assert chunk_data["items"][0]["model"] == "test/bge-small-zh"
    assert {item["knowledgeType"] for item in chunk_data["items"]} == {
        "strengths",
        "project",
    }
    project_item = next(
        item
        for item in chunk_data["items"]
        if item["entityId"] == str(project_response.json()["id"])
    )
    assert project_item["sourceId"] == str(project_response.json()["id"])
    assert project_item["tags"] == ["Python", "RAG"]
    assert all("机械切片" not in item["content"] for item in chunk_data["items"])

    search = client.post("/v1/rag/search", json={"query": "Python 后端", "limit": 2})
    assert search.status_code == 200
    items = search.json()["items"]
    assert len(items) == 2
    assert items[0]["sourceName"] in {"个人档案", "企业知识库"}
    assert items[0]["score"] >= items[1]["score"]
    assert "vectorScore" in items[0]
    assert "keywordScore" in items[0]
    assert any(item["keywordScore"] > 0 for item in items)

    deleted_id = project_item["id"]
    deleted = client.delete(f"/v1/rag/chunks/{deleted_id}")
    assert deleted.status_code == 204
    remaining = client.get("/v1/rag/chunks").json()["items"]
    assert all(item["id"] != deleted_id for item in remaining)
    assert client.delete(f"/v1/rag/chunks/{deleted_id}").status_code == 404

    matched = client.post(
        "/v1/jobs/match",
        json={
            "title": "Python 后端工程师",
            "jobText": "负责 Python、FastAPI 和 RAG 服务开发",
            "skills": ["Python", "FastAPI", "RAG"],
            "minimumSuitabilityScore": 1,
            "minimumCustomizationConfidence": 1,
        },
    )
    assert matched.status_code == 200
    match_data = matched.json()
    assert match_data["suitabilityScore"] > 0
    assert match_data["customizationConfidence"] > 0
    assert match_data["decision"]["materialStrategy"] == "custom"
    assert match_data["evidence"]
    assert match_data["scoringVersion"] == "local-hybrid-v1"

    risk_match = client.post(
        "/v1/jobs/match",
        json={
            "jobText": "要求 985、211 院校优先，负责 Python 后端开发",
            "minimumSuitabilityScore": 1,
            "minimumCustomizationConfidence": 1,
        },
    )
    assert risk_match.status_code == 200
    assert risk_match.json()["decision"]["materialStrategy"] == "default"


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


def test_rag_uses_materialized_profile_entities_instead_of_raw_sections(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    saved = client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "• 熟悉 Python 后端开发\n• 具备 RAG 检索优化经验",
                "techStack": (
                    "Agent 与编排：LangGraph、LangChain、MCP\n"
                    "RAG 与推理：Embedding、Rerank"
                ),
                "workExperience": "示例公司 · AI 工程师 · 2024-至今",
                "education": "示例大学 · 计算机科学 · 本科",
            }
        },
    )
    profile = saved.json()["data"]
    assert [item["content"] for item in profile["strengths"]] == [
        "熟悉 Python 后端开发",
        "具备 RAG 检索优化经验",
    ]
    assert profile["techStackGroups"][0]["name"] == "Agent 与编排"
    assert profile["techStackGroups"][0]["items"] == ["LangGraph", "LangChain", "MCP"]

    chunks = client.get("/v1/rag/chunks").json()["items"]
    assert len([item for item in chunks if item["knowledgeType"] == "strengths"]) == 2
    assert len([item for item in chunks if item["knowledgeType"] == "tech-stack"]) == 2
    assert all(item["content"] != profile["summary"] for item in chunks)
    tech_chunk = next(item for item in chunks if item["sourceName"] == "Agent 与编排")
    assert tech_chunk["tags"] == ["LangGraph", "LangChain", "MCP"]


def test_structured_profile_stops_at_following_resume_headings(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    saved = client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "优势一\n优势二\n技术栈\nAgent 与编排：LangGraph",
                "techStack": (
                    "Agent 与编排：LangGraph、MCP\n"
                    "RAG 与推理：Embedding、Rerank\n"
                    "美团到餐 AI Agent 项目实践\n项目详情不应进入技术栈"
                ),
            }
        },
    )
    profile = saved.json()["data"]
    assert [item["content"] for item in profile["strengths"]] == ["优势一", "优势二"]
    assert [item["name"] for item in profile["techStackGroups"]] == [
        "Agent 与编排",
        "RAG 与推理",
    ]
