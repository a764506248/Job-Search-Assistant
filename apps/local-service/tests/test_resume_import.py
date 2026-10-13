from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from job_search_assistant.main import create_app


class FakeEmbedder:
    model = "test/local-matcher"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]


def make_pdf(text: str) -> bytes:
    stream = BytesIO()
    document = canvas.Canvas(stream)
    document.drawString(72, 760, text)
    document.showPage()
    document.save()
    return stream.getvalue()


class FakeProjectExtractor:
    def extract(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> list[dict[str, object]]:
        assert "企业知识库问答系统" in resume_text
        assert model_record_id is None
        return [
            {
                "name": "企业知识库问答系统",
                "data": {
                    "summary": "构建企业知识库问答服务",
                    "role": "负责 RAG 后端开发",
                    "technologies": ["Python", "FastAPI", "LangGraph"],
                    "achievements": ["完成知识检索链路"],
                    "tags": "Python,FastAPI,LangGraph,RAG",
                    "evidence": "使用 Python、FastAPI、LangGraph 构建 RAG 服务",
                    "extractionMethod": "ai",
                },
            }
        ]


class StructuredResumeExtractor:
    def extract_resume(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> dict[str, object]:
        return {
            "profile": {
                "displayName": "AI 提取姓名",
                "strengths": [{"id": "strength-1", "content": "完整的个人优势"}],
                "summary": "完整的个人优势",
                "workExperiences": [{
                    "id": "work-1", "company": "示例公司", "content": "公司：示例公司"
                }],
                "workExperience": "公司：示例公司",
            },
            "projects": [
                {"name": "项目一", "data": {"summary": "完整项目一", "extractionMethod": "ai"}},
                {"name": "项目二", "data": {"summary": "完整项目二", "extractionMethod": "ai"}},
            ],
            "modelRecordId": 2,
            "modelName": "兜底模型",
            "modelId": "fallback-model",
            "attemptErrors": ["主模型：timed out"],
        }


class MutableStructuredResumeExtractor:
    def __init__(self) -> None:
        self.projects = [
            {"name": "已有项目", "data": {"summary": "第一版", "extractionMethod": "ai"}},
        ]

    def extract_resume(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> dict[str, object]:
        return {
            "profile": {},
            "projects": self.projects,
            "modelRecordId": 1,
            "modelName": "测试模型",
            "modelId": "test-model",
            "attemptErrors": [],
        }


def test_ai_resume_import_accumulates_projects_without_resetting_or_duplicating(
    tmp_path,
) -> None:
    extractor = MutableStructuredResumeExtractor()
    client = TestClient(create_app(
        tmp_path / "jobs.sqlite3",
        embedder=FakeEmbedder(),
        project_extractor=extractor,
    ))

    first = client.post(
        "/v1/resumes/import",
        files={"file": ("resume-v1.txt", "第一版简历".encode(), "text/plain")},
    ).json()
    assert first["confirmationStatus"] == "pending"
    first_confirmed = client.post(f"/v1/resumes/{first['resumeId']}/confirm").json()
    first_project_id = first_confirmed["projectIds"][0]

    extractor.projects = [
        {"name": "已有 项目", "data": {"summary": "第二版", "extractionMethod": "ai"}},
        {"name": "新增项目", "data": {"summary": "新增内容", "extractionMethod": "ai"}},
    ]
    second = client.post(
        "/v1/resumes/import",
        files={"file": ("resume-v2.txt", "第二版简历".encode(), "text/plain")},
    ).json()
    second_confirmed = client.post(f"/v1/resumes/{second['resumeId']}/confirm").json()

    projects = client.get("/v1/library/projects").json()["items"]
    assert len(projects) == 2
    assert second_confirmed["projectIds"][0] == first_project_id
    assert {item["name"] for item in projects} == {"已有 项目", "新增项目"}
    updated = next(item for item in projects if item["id"] == first_project_id)
    assert updated["data"]["summary"] == "第二版"


def test_pdf_import_generates_first_page_image_and_supports_default_selection(
    tmp_path,
) -> None:
    client = TestClient(create_app(
        tmp_path / "jobs.sqlite3",
        embedder=FakeEmbedder(),
        project_extractor=StructuredResumeExtractor(),
    ))
    first = client.post(
        "/v1/resumes/import",
        files={"file": ("resume-one.pdf", make_pdf("First resume page"), "application/pdf")},
    ).json()
    second = client.post(
        "/v1/resumes/import",
        files={"file": ("resume-two.pdf", make_pdf("Second resume page"), "application/pdf")},
    ).json()
    assert client.get("/v1/resumes/default-image").status_code == 404
    client.post(f"/v1/resumes/{first['resumeId']}/confirm")
    client.post(f"/v1/resumes/{second['resumeId']}/confirm")

    records = client.get("/v1/library/resumes").json()["items"]
    first_record = next(item for item in records if item["id"] == first["resumeId"])
    second_record = next(item for item in records if item["id"] == second["resumeId"])
    assert first_record["data"]["isDefaultImage"] is True
    assert second_record["data"]["isDefaultImage"] is False
    assert first_record["data"]["previewImageFile"].endswith("-page-1.png")

    preview = client.get(f"/v1/resumes/{first['resumeId']}/preview-image")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")

    selected = client.put(f"/v1/resumes/{second['resumeId']}/default-image")
    assert selected.status_code == 200
    assert selected.json()["data"]["isDefaultImage"] is True
    default_image = client.get("/v1/resumes/default-image")
    assert default_image.status_code == 200
    assert default_image.content == client.get(
        f"/v1/resumes/{second['resumeId']}/preview-image"
    ).content


def test_import_resume_uses_full_structured_result_and_reports_fallback(tmp_path) -> None:
    client = TestClient(create_app(
        tmp_path / "jobs.sqlite3",
        embedder=FakeEmbedder(),
        project_extractor=StructuredResumeExtractor(),
    ))
    response = client.post(
        "/v1/resumes/import",
        files={"file": ("resume.txt", "原始姓名\n项目经历\n项目一\n项目二".encode(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["aiProfileExtracted"] is True
    assert result["aiProjectCount"] == 2
    assert result["aiModelName"] == "兜底模型"
    assert result["aiAttemptErrors"] == ["主模型：timed out"]
    assert result["confirmationRequired"] is True
    assert client.get("/v1/profile").json()["data"] == {}
    confirmation = client.post(f"/v1/resumes/{result['resumeId']}/confirm")
    assert confirmation.status_code == 200
    profile = client.get("/v1/profile").json()["data"]
    assert profile["displayName"] == "AI 提取姓名"
    assert profile["strengths"] == [{"id": "strength-1", "content": "完整的个人优势"}]
    projects = client.get("/v1/library/projects").json()["items"]
    assert len(projects) == 2
    assert {item["name"] for item in projects} == {"项目一", "项目二"}
    assert all(item["data"]["source"] == "resume-import" for item in projects)

def test_import_resume_writes_profile_projects_and_resume(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=FakeEmbedder(),
            project_extractor=FakeProjectExtractor(),
        )
    )
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
    assert result["projectIds"] == []
    assert client.get("/v1/profile").json()["data"] == {}
    pending_setup = client.get("/v1/setup/status").json()
    pending_resume = next(
        item for item in pending_setup["checks"] if item["key"] == "resume"
    )
    assert pending_resume["status"] == "blocked"
    assert "等待确认" in pending_resume["message"]
    confirmed = client.post(f"/v1/resumes/{result['resumeId']}/confirm").json()
    assert len(confirmed["projectIds"]) == 1
    ready_setup = client.get("/v1/setup/status").json()
    ready_resume = next(item for item in ready_setup["checks"] if item["key"] == "resume")
    assert ready_resume["status"] == "ready"
    assert result["aiExtractionUsed"] is True
    assert result["aiProjectCount"] == 1
    assert result["aiExtractionError"] is None

    profile = client.get("/v1/profile").json()["data"]
    assert profile["displayName"] == "张小林"
    assert profile["targetRoles"] == "AI 应用开发工程师"
    assert profile["phone"] == "13800138000"
    assert profile["email"] == "xiaolin@example.com"
    assert profile["yearsExperience"] == "5"

    projects = client.get("/v1/library/projects").json()["items"]
    assert len(projects) == 1
    assert projects[0]["name"] == "企业知识库问答系统"
    assert projects[0]["data"]["role"] == "负责 RAG 后端开发"
    assert projects[0]["data"]["extractionMethod"] == "ai"
    assert "Python" in projects[0]["data"]["tags"]

    resumes = client.get("/v1/library/resumes").json()["items"]
    assert len(resumes) == 1
    assert resumes[0]["data"]["fileName"] == "张小林简历.txt"
    assert "rawText" in resumes[0]["data"]

    repeated = client.post(
        "/v1/resumes/import",
        files={"file": ("张小林简历.txt", content.encode(), "text/plain")},
    ).json()
    repeated_confirmed = client.post(
        f"/v1/resumes/{repeated['resumeId']}/confirm"
    ).json()
    assert repeated_confirmed["projectIds"] == confirmed["projectIds"]
    assert len(client.get("/v1/library/projects").json()["items"]) == 1


class SelectedModelProjectExtractor:
    def __init__(self) -> None:
        self.model_record_id: int | None = None

    def extract(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> list[dict[str, object]]:
        self.model_record_id = model_record_id
        return [{"name": "AI 项目", "data": {"summary": "模型提取结果"}}]


def test_import_resume_uses_selected_model_and_reports_it(tmp_path) -> None:
    extractor = SelectedModelProjectExtractor()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=FakeEmbedder(),
            project_extractor=extractor,
        )
    )
    model_response = client.post(
        "/v1/library/models",
        json={
            "name": "项目识别模型",
            "data": {
                "provider": "OpenAI Compatible",
                "modelId": "project-extractor-v1",
                "apiKey": "sk-test",
                "baseUrl": "https://api.example.com/v1",
            },
        },
    )
    model_record_id = model_response.json()["id"]

    response = client.post(
        "/v1/resumes/import",
        data={"modelRecordId": str(model_record_id)},
        files={"file": ("resume.txt", "项目经历\nAI 项目".encode(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert extractor.model_record_id == model_record_id
    assert result["aiModelRecordId"] == model_record_id
    assert result["aiModelName"] == "项目识别模型"
    assert result["aiModelId"] == "project-extractor-v1"
    assert result["aiExtractionUsed"] is True


def test_import_resume_rejects_unsupported_file(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=FakeEmbedder()))
    response = client.post(
        "/v1/resumes/import",
        files={"file": ("resume.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400
    assert "仅支持" in response.json()["detail"]


class FailingProjectExtractor:
    def extract(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> list[dict[str, object]]:
        raise RuntimeError("模型接口暂时不可用")


def test_import_resume_keeps_data_when_ai_extraction_fails(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=FakeEmbedder(),
            project_extractor=FailingProjectExtractor(),
        )
    )
    content = """测试用户
项目经历
本地降级项目
使用 Python 完成服务。
工作经历
示例公司
"""

    response = client.post(
        "/v1/resumes/import",
        files={"file": ("fallback.txt", content.encode(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["aiExtractionUsed"] is False
    assert result["aiExtractionError"] == "模型接口暂时不可用"
    confirmed = client.post(f"/v1/resumes/{result['resumeId']}/confirm").json()
    assert len(confirmed["projectIds"]) == 1


class EmptyProjectExtractor:
    def extract(
        self,
        resume_text: str,
        model_record_id: int | None = None,
        *,
        user_id: int = 1,
    ) -> list[dict[str, object]]:
        return []


def test_import_resume_splits_projects_when_ai_returns_empty(
    tmp_path,
) -> None:
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=FakeEmbedder(),
            project_extractor=EmptyProjectExtractor(),
        )
    )
    content = """测试用户
项目经历
实时语音导购 Agent 核心开发 2025.03 - 2026.07
串联 RTC、ASR、RAG、LLM 与 TTS，完成实时导购。
检索速度提升 4 倍。
内容运营系统 项目负责人 2024.01 - 2025.02
使用 LangGraph 构建选题、写作和审核工作流。
整体生成耗时缩减 70%。
工作经历
示例公司
"""

    response = client.post(
        "/v1/resumes/import",
        files={"file": ("multi-project.txt", content.encode(), "text/plain")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["aiExtractionUsed"] is False
    assert "本地项目标题规则" in result["aiExtractionError"]
    confirmed = client.post(f"/v1/resumes/{result['resumeId']}/confirm").json()
    assert len(confirmed["projectIds"]) == 2

    projects = client.get("/v1/library/projects").json()["items"]
    assert {item["name"] for item in projects} == {
        "实时语音导购 Agent",
        "内容运营系统",
    }
    reprocess = client.post(f"/v1/resumes/{result['resumeId']}/extract-projects")
    assert reprocess.status_code == 200
    assert reprocess.json()["projectIds"] == confirmed["projectIds"]
    assert reprocess.json()["extractionMethod"] == "local-heading-fallback"
