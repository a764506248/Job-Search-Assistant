from job_search_assistant.project_extraction import CloudGreetingGenerator, CloudProjectExtractor
from job_search_assistant.repositories import LibraryRepository


def test_greeting_generator_parses_only_greeting() -> None:
    assert CloudGreetingGenerator._parse('{"greeting":"您好，希望进一步沟通。"}') == (
        "您好，希望进一步沟通。"
    )


def test_cloud_project_extractor_uses_saved_model_config(tmp_path, monkeypatch) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    library.create(
        "models",
        "主模型",
        {
            "provider": "OpenAI Compatible",
            "modelId": "test-model",
            "apiKey": "sk-test",
            "baseUrl": "https://api.example.com/v1",
        },
    )
    captured = {}

    def fake_request(url, payload, headers):
        captured.update(url=url, payload=payload, headers=headers)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"projects":[{"name":"RAG 平台","summary":"知识检索",'
                            '"role":"后端开发","technologies":["Python","RAG"],'
                            '"achievements":["完成检索"],"tags":["AI"],'
                            '"startDate":"","endDate":"","evidence":"原文"}]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(CloudProjectExtractor, "_request_json", staticmethod(fake_request))

    projects = CloudProjectExtractor(library).extract("RAG 平台项目原文")

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "test-model"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert projects[0]["name"] == "RAG 平台"
    assert projects[0]["data"]["extractionMethod"] == "ai"
    assert projects[0]["data"]["tags"] == "Python,RAG,AI"


def test_cloud_project_extractor_requires_model_configuration(tmp_path) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")

    try:
        CloudProjectExtractor(library).extract("项目原文")
    except RuntimeError as error:
        assert "尚未配置云端模型" in str(error)
    else:
        raise AssertionError("missing model configuration must fail explicitly")


def test_cloud_project_extractor_uses_selected_model_config(tmp_path, monkeypatch) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    library.create(
        "models",
        "默认模型",
        {"provider": "OpenAI", "modelId": "first", "apiKey": "key-1", "baseUrl": "https://first.example/v1"},
    )
    selected = library.create(
        "models",
        "项目提取模型",
        {"provider": "OpenAI Compatible", "modelId": "selected", "apiKey": "key-2", "baseUrl": "https://selected.example/v1"},
    )
    captured = {}

    def fake_request(url, payload, headers):
        captured.update(url=url, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": '{"projects":[]}'}}]}

    monkeypatch.setattr(CloudProjectExtractor, "_request_json", staticmethod(fake_request))

    CloudProjectExtractor(library).extract("项目原文", selected["id"])

    assert captured["url"] == "https://selected.example/v1/chat/completions"
    assert captured["payload"]["model"] == "selected"
    assert captured["headers"]["Authorization"] == "Bearer key-2"


def test_full_resume_prompt_extracts_profile_and_multiple_projects(tmp_path, monkeypatch) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    library.create(
        "models",
        "主模型",
        {
            "usageRole": "primary",
            "provider": "OpenAI Compatible",
            "modelId": "primary-model",
            "apiKey": "key",
            "baseUrl": "https://primary.example/v1",
        },
    )

    def fake_request(url, payload, headers):
        assert "一个有独立名称" in payload["messages"][1]["content"]
        assert "workExperiences" in payload["messages"][1]["content"]
        return {"choices": [{"message": {"content": """{
          "profile": {
            "displayName": "张三",
            "strengths": [{"content": "熟悉 RAG 工程落地", "evidence": "熟悉 RAG 工程落地"}],
            "techStackGroups": [{"name": "AI", "items": ["RAG", "LangGraph"]}],
            "workExperiences": [{"company": "示例公司", "role": "AI 工程师",
              "achievements": ["交付智能问答"]}],
            "educations": [{"school": "示例大学", "degree": "本科"}]
          },
          "projects": [
            {"name": "知识库系统", "summary": "企业问答",
              "responsibilities": ["检索链路"], "technologies": ["RAG"]},
            {"name": "语音 Agent", "summary": "实时导购",
              "responsibilities": ["RTC 链路"], "technologies": ["RTC"]}
          ]
        }"""}}]}

    monkeypatch.setattr(CloudProjectExtractor, "_request_json", staticmethod(fake_request))
    result = CloudProjectExtractor(library).extract_resume("完整简历")

    assert result["profile"]["displayName"] == "张三"
    assert len(result["profile"]["workExperiences"]) == 1
    assert [project["name"] for project in result["projects"]] == ["知识库系统", "语音 Agent"]
    assert result["projects"][0]["data"]["responsibilities"] == ["检索链路"]


def test_primary_failure_automatically_uses_fallback_model(tmp_path, monkeypatch) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    primary = library.create(
        "models",
        "主模型",
        {
            "usageRole": "primary", "provider": "OpenAI Compatible",
            "modelId": "primary", "apiKey": "key-1", "baseUrl": "https://primary.example/v1",
        },
    )
    fallback = library.create(
        "models",
        "兜底模型",
        {
            "usageRole": "fallback", "provider": "OpenAI Compatible",
            "modelId": "fallback", "apiKey": "key-2", "baseUrl": "https://fallback.example/v1",
        },
    )

    def fake_request(url, payload, headers):
        if "primary.example" in url:
            raise RuntimeError("模型接口调用失败: timed out")
        return {
            "choices": [{"message": {
                "content": '{"profile":{"displayName":"李四"},"projects":[]}'
            }}]
        }

    monkeypatch.setattr(CloudProjectExtractor, "_request_json", staticmethod(fake_request))
    result = CloudProjectExtractor(library).extract_resume("简历", primary["id"])

    assert result["modelRecordId"] == fallback["id"]
    assert result["modelId"] == "fallback"
    assert "timed out" in result["attemptErrors"][0]


def test_second_model_is_default_fallback_before_roles_are_configured(
    tmp_path, monkeypatch
) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    fallback = library.create(
        "models",
        "旧备用模型",
        {
            "provider": "OpenAI Compatible", "modelId": "old-fallback",
            "apiKey": "key-1", "baseUrl": "https://fallback.example/v1",
        },
    )
    primary = library.create(
        "models",
        "最近使用模型",
        {
            "provider": "OpenAI Compatible", "modelId": "recent-primary",
            "apiKey": "key-2", "baseUrl": "https://primary.example/v1",
        },
    )

    def fake_request(url, payload, headers):
        if "primary.example" in url:
            raise RuntimeError("timed out")
        return {"choices": [{"message": {
            "content": '{"profile":{},"projects":[]}'
        }}]}

    monkeypatch.setattr(CloudProjectExtractor, "_request_json", staticmethod(fake_request))
    result = CloudProjectExtractor(library).extract_resume("简历", primary["id"])

    assert result["modelRecordId"] == fallback["id"]


def test_model_roles_are_unique(tmp_path) -> None:
    library = LibraryRepository(tmp_path / "assistant.sqlite3")
    first = library.create("models", "主模型一", {"usageRole": "primary"})
    second = library.create("models", "主模型二", {"usageRole": "primary"})

    assert library.get("models", first["id"])["data"]["usageRole"] == "available"
    assert library.get("models", second["id"])["data"]["usageRole"] == "primary"
