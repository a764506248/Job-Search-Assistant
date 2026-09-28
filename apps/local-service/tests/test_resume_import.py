from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


class FakeEmbedder:
    model = "test/resume-embedding"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]


def test_import_resume_writes_profile_projects_resume_and_vectors(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    content = """张小林
目标岗位：AI 应用开发工程师
13800138000
xiaolin@example.com
5 年工作经验
期望城市：上海
个人优势
熟悉 Python、FastAPI 与 RAG 应用开发。
项目经历
企业知识库问答系统
使用 Python、FastAPI、LangGraph 和 PostgreSQL 构建 RAG 服务。
工作经历
示例科技有限公司 AI 工程师
教育经历
示例大学 计算机科学 本科
"""

    response = client.post(
        "/v1/resumes/import",
        files={"file": ("张小林简历.txt", content.encode(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["indexRebuilt"] is True
    assert result["indexedChunks"] >= 3
    assert len(result["projectIds"]) == 1

    profile = client.get("/v1/profile").json()["data"]
    assert profile["displayName"] == "张小林"
    assert profile["targetRoles"] == "AI 应用开发工程师"
    assert profile["phone"] == "13800138000"
    assert profile["email"] == "xiaolin@example.com"
    assert profile["yearsExperience"] == "5"

    projects = client.get("/v1/library/projects").json()["items"]
    assert len(projects) == 1
    assert "企业知识库问答系统" in projects[0]["data"]["summary"]
    assert "Python" in projects[0]["data"]["tags"]

    resumes = client.get("/v1/library/resumes").json()["items"]
    assert len(resumes) == 1
    assert resumes[0]["data"]["fileName"] == "张小林简历.txt"
    assert "rawText" in resumes[0]["data"]

    chunks = client.get("/v1/rag/chunks").json()
    assert chunks["total"] >= 3
    assert {item["dimensions"] for item in chunks["items"]} == {3}


def test_import_resume_rejects_unsupported_file(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    response = client.post(
        "/v1/resumes/import",
        files={"file": ("resume.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400
    assert "仅支持" in response.json()["detail"]
