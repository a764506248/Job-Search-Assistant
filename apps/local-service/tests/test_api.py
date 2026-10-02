from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


class MaterialPreviewEmbedder:
    model = "test/material-preview"

    def health(self) -> dict[str, object]:
        return {"status": "ok", "model": self.model}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(text.count("RAG")), 1.0, 0.5] for text in texts]


class FakeMaterialPreviewGenerator:
    def __init__(self) -> None:
        self.context: dict[str, object] = {}

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        self.context = context
        return {
            "modelRecordId": 7,
            "modelName": "测试模型",
            "modelId": "test-model",
            "greeting": "您好，我有 RAG 与 Agent 项目经验，与岗位需求匹配。",
            "resume": {
                "headline": "AI Agent 工程师",
                "summary": ["具备 RAG 项目经验"],
                "skills": ["Python", "RAG"],
                "projects": ["企业知识库：负责 RAG 检索"],
                "workExperience": ["示例公司 · AI 工程师"],
                "education": ["示例大学 · 本科"],
                "optimizationNotes": ["优先展示 RAG 项目"],
            },
        }


class FakeGreetingGenerator:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.contexts: list[dict[str, object]] = []

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        self.contexts.append(context)
        if self.error:
            raise RuntimeError(self.error)
        return {
            "modelRecordId": 9,
            "modelName": "问候语测试模型",
            "modelId": "test-greeting",
            "greeting": "您好，我有 RAG 与 Agent 项目经验，希望进一步沟通岗位需求。",
        }


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_setup_status_reports_actionable_first_run_checks(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )

    response = client.get("/v1/setup/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"] == "blocked"
    assert payload["total"] == 8
    checks = {item["key"]: item for item in payload["checks"]}
    assert checks["local-service"]["status"] == "ready"
    assert checks["embedding"]["status"] == "ready"
    assert checks["model"]["status"] == "blocked"
    assert checks["resume"]["actionPath"] == "/resumes"
    assert checks["browser"]["status"] == "pending"
    assert payload["checkedAt"]


def test_extension_error_log_is_stored_locally(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "source": "extension-content",
        "level": "error",
        "event": "job-analysis-failed",
        "message": "Local service request failed: 503",
        "pageUrl": "https://www.zhipin.com/job_detail/example.html",
        "platformJobId": "example",
        "occurredAt": "2026-09-28T09:00:00Z",
    }

    created = client.post("/v1/client-logs", json=payload)
    assert created.status_code == 201
    assert created.json()["id"] == 1

    listing = client.get("/v1/client-logs")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["event"] == "job-analysis-failed"
    assert listing.json()["items"][0]["message"] == payload["message"]


def test_boss_content_script_origin_can_access_local_service(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.options(
        "/v1/jobs/match",
        headers={
            "Origin": "https://www.zhipin.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://www.zhipin.com"
    assert response.headers["access-control-allow-private-network"] == "true"


def test_unrelated_web_origin_cannot_access_local_service(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.options(
        "/v1/jobs/match",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_backend_is_api_only(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    assert client.get("/").status_code == 404
    assert client.get("/models").status_code == 404
    assert client.get("/v1/health").status_code == 200


def test_decision_api_accepts_camel_case_contract(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/decisions/evaluate",
        json={
            "jobText": "负责 RAG 应用研发",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
        },
    )

    assert response.status_code == 200
    assert response.json()["materialStrategy"] == "custom"


def test_capture_job_is_idempotent(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "jobs": [
            {
                "platform": "boss",
                "platformJobId": "job-123",
                "url": "https://www.zhipin.com/job_detail/job-123.html",
                "title": "AI 应用开发工程师",
                "companyName": "示例公司",
                "description": "负责 RAG 应用研发",
                "skills": ["Python", "RAG"],
                "capturedAt": "2026-09-28T08:00:00Z",
                "source": "dom",
            }
        ]
    }

    first = client.post("/v1/jobs/capture", json=payload)
    payload["jobs"][0].update(
        {
            "location": "北京",
            "workAddress": "北京市丰台区汉威国际广场四区 1 号楼 7 层",
            "salaryText": "25-50K",
            "companySize": "100-499人",
            "experience": "5-10年",
            "education": "本科",
            "description": "负责 RAG 应用研发与 Agent 平台建设",
        }
    )
    second = client.post("/v1/jobs/capture", json=payload)

    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "jobIds": ["job-123"]}
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "jobIds": []}

    listing = client.get("/v1/jobs")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    item = listing.json()["items"][0]
    assert item["salaryText"] == "25-50K"
    assert item["companySize"] == "100-499人"
    assert item["location"] == "北京"
    assert item["workAddress"] == "北京市丰台区汉威国际广场四区 1 号楼 7 层"
    assert item["experience"] == "5-10年"
    assert item["education"] == "本科"
    assert item["description"] == "负责 RAG 应用研发与 Agent 平台建设"
    snapshot_id = item["id"]

    deleted = client.delete(f"/v1/jobs/{snapshot_id}")
    assert deleted.status_code == 204
    assert client.get("/v1/jobs").json()["total"] == 0


def test_job_snapshots_support_server_side_pagination_and_search(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    for index in range(1, 6):
        response = client.post(
            "/v1/jobs",
            json={
                "title": f"AI Agent 工程师 {index}",
                "companyName": "分页测试公司" if index <= 3 else "其他公司",
                "description": f"负责第 {index} 个 RAG 项目",
            },
        )
        assert response.status_code == 201

    first_page = client.get("/v1/jobs?page=1&pageSize=2").json()
    assert first_page["total"] == 5
    assert first_page["page"] == 1
    assert first_page["pageSize"] == 2
    assert first_page["totalPages"] == 3
    assert [item["title"] for item in first_page["items"]] == [
        "AI Agent 工程师 5",
        "AI Agent 工程师 4",
    ]

    last_page = client.get("/v1/jobs?page=3&pageSize=2").json()
    assert last_page["page"] == 3
    assert [item["title"] for item in last_page["items"]] == ["AI Agent 工程师 1"]

    searched = client.get(
        "/v1/jobs",
        params={"page": 1, "pageSize": 2, "query": "分页测试公司"},
    ).json()
    assert searched["total"] == 3
    assert searched["totalPages"] == 2
    assert len(searched["items"]) == 2

    first_id = first_page["items"][0]["id"]
    tracked = client.put(
        f"/v1/jobs/{first_id}/tracking",
        json={
            "hasCommunicated": True,
            "hasInterview": True,
            "resumeVariant": "default",
        },
    )
    assert tracked.status_code == 200

    communicated = client.get(
        "/v1/jobs", params={"communicationResult": "communicated"}
    ).json()
    assert communicated["total"] == 1
    assert communicated["items"][0]["id"] == first_id

    not_communicated = client.get(
        "/v1/jobs", params={"communicationResult": "not_communicated"}
    ).json()
    assert not_communicated["total"] == 4

    interviewed = client.get(
        "/v1/jobs", params={"communicationResult": "interviewed"}
    ).json()
    assert interviewed["total"] == 1


def test_create_manual_job_snapshot(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "未来智能科技",
            "companySize": "500-999人",
            "location": "北京",
            "workAddress": "北京市海淀区中关村软件园",
            "salaryText": "25-40K·14薪",
            "experience": "3-5年",
            "education": "本科",
            "description": "负责基于 LangGraph 和 RAG 的 AI Agent 平台研发。",
            "skills": ["Python", "FastAPI", "LangGraph", "RAG"],
            "recruiterName": "李女士",
            "recruiterTitle": "招聘经理",
        },
    )

    assert response.status_code == 201
    result = response.json()
    assert result["source"] == "manual"
    assert result["companySize"] == "500-999人"
    assert result["workAddress"] == "北京市海淀区中关村软件园"
    assert result["platformJobId"].startswith("manual-")
    assert result["contentHash"]
    assert result["hasCommunicated"] is False
    assert result["hasInterview"] is False
    assert result["resumeVariant"] == "default"

    tracking = client.put(
        f"/v1/jobs/{result['id']}/tracking",
        json={
            "hasCommunicated": True,
            "hasInterview": True,
            "generatedGreeting": "您好，我有 RAG 与 Agent 项目经验。",
            "resumeVariant": "optimized",
            "generatedResumeId": 12,
            "resumeOptimization": "突出 LangGraph、RAG 和 FastAPI 项目成果。",
        },
    )
    assert tracking.status_code == 200
    tracked = tracking.json()
    assert tracked["hasCommunicated"] is True
    assert tracked["hasInterview"] is True
    assert tracked["generatedGreeting"].startswith("您好")
    assert tracked["generatedResumeId"] == 12
    assert tracked["resumeVariant"] == "optimized"
    assert client.get("/v1/jobs").json()["items"][0]["title"] == "AI Agent 工程师"


def test_job_snapshot_automatically_generates_and_stores_greeting(tmp_path) -> None:
    generator = FakeGreetingGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={"data": {"summary": "熟悉 RAG 开发", "defaultGreeting": "默认问候语"}},
    )
    client.post(
        "/v1/library/projects",
        json={"name": "知识库项目", "data": {"summary": "RAG 检索", "tags": "RAG"}},
    )

    created = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "description": "负责 Agent 与 RAG 平台研发",
            "skills": ["Python", "RAG"],
        },
    )

    assert created.status_code == 201
    stored = client.get("/v1/jobs").json()["items"][0]
    assert stored["generatedGreeting"].startswith("您好")
    assert generator.contexts[0]["defaultGreeting"] == "默认问候语"
    assert generator.contexts[0]["profile"]["summary"] == "熟悉 RAG 开发"
    assert generator.contexts[0]["vectorEvidence"]
    assert "defaultResume" not in generator.contexts[0]


def test_job_snapshot_falls_back_to_default_greeting_without_blocking(tmp_path) -> None:
    generator = FakeGreetingGenerator("模型超时")
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={"data": {"defaultGreeting": "您好，我对贵司岗位很感兴趣。"}},
    )

    created = client.post(
        "/v1/jobs",
        json={
            "title": "Python 工程师",
            "companyName": "示例科技",
            "description": "负责 Python 服务开发",
        },
    )

    assert created.status_code == 201
    stored = client.get("/v1/jobs").json()["items"][0]
    assert stored["generatedGreeting"] == "您好，我对贵司岗位很感兴趣。"


def test_preview_job_materials_combines_all_local_sources(tmp_path) -> None:
    generator = FakeMaterialPreviewGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            material_preview_generator=generator,
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "defaultGreeting": "您好，我对贵司岗位很感兴趣。",
                "workExperience": "示例公司 · AI 工程师",
                "education": "示例大学 · 本科",
            }
        },
    )
    client.post(
        "/v1/library/projects",
        json={
            "name": "企业知识库",
            "data": {"summary": "负责 RAG 检索服务", "tags": "RAG,Python"},
        },
    )
    client.post(
        "/v1/library/resumes",
        json={"name": "默认简历", "data": {"rawText": "默认简历原文"}},
    )
    job = client.post(
        "/v1/jobs",
        json={
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "description": "负责 Agent 与 RAG 平台研发",
            "skills": ["Python", "RAG"],
        },
    ).json()

    response = client.post(f"/v1/jobs/{job['id']}/material-preview", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["greeting"].startswith("您好")
    assert result["resume"]["projects"] == ["企业知识库：负责 RAG 检索"]
    assert result["match"]["evidence"]
    assert generator.context["job"]["description"] == "负责 Agent 与 RAG 平台研发"
    assert generator.context["profile"]["defaultGreeting"].startswith("您好")
    assert generator.context["vectorEvidence"]
    assert generator.context["defaultResume"]["rawText"] == "默认简历原文"


def test_delivery_api_upserts_by_platform_job_id(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    payload = {
        "platform": "boss",
        "platformJobId": "boss-job-1",
        "title": "AI Agent 开发工程师",
        "companyName": "示例公司",
        "salaryText": "20-40K",
        "location": "北京",
        "recruiterName": "罗女士",
        "status": "delivered",
        "decision": "APPROVE",
        "reason": "匹配 AI Agent 与 RAG 经验",
        "greetingText": "您好，方便沟通吗？",
        "detail": "问候语已发送",
        "appliedAt": "2026-09-29T09:00:00Z",
        "metadata": {"source": "boss-zhipin-deliver"},
    }

    first = client.post("/v1/deliveries", json=payload)
    assert first.status_code == 201
    assert first.json()["status"] == "delivered"

    payload["status"] = "greeting_sent"
    payload["detail"] = "问候语已送达"
    second = client.post("/v1/deliveries", json=payload)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "greeting_sent"

    listing = client.get("/v1/deliveries")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["platformJobId"] == "boss-job-1"


def test_automation_config_uses_profile_and_library_rules(tmp_path) -> None:
    client = TestClient(
        create_app(tmp_path / "jobs.sqlite3", embedder=MaterialPreviewEmbedder())
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "targetRoles": ["AI Agent 工程师"],
                "cities": ["北京"],
                "defaultGreeting": "您好，想和您沟通这个岗位。",
                "minimumSuitabilityScore": 60,
                "minimumCustomizationConfidence": 80,
            }
        },
    )
    client.post(
        "/v1/library/rules",
        json={
            "name": "屏蔽外包",
            "data": {"pattern": "外包, 驻场", "action": "block_delivery"},
        },
    )

    response = client.get("/v1/automation/config")

    assert response.status_code == 200
    result = response.json()
    assert result["searchKeywords"] == ["AI Agent 工程师"]
    assert result["targetCities"] == ["北京"]
    assert result["cityCode"] == "101010100"
    assert result["minimumSuitabilityScore"] == 60
    assert result["matchingRules"][0]["patterns"] == ["外包", "驻场"]


def test_automation_config_prefers_explicit_boss_city_code(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    client.put(
        "/v1/profile",
        json={"data": {"cities": ["北京"], "bossCityCode": "custom-code"}},
    )

    result = client.get("/v1/automation/config").json()

    assert result["cityCode"] == "custom-code"


def test_analyze_and_plan_atomically_saves_matches_and_generates_greeting(tmp_path) -> None:
    greeting_generator = FakeGreetingGenerator()
    client = TestClient(
        create_app(
            tmp_path / "jobs.sqlite3",
            embedder=MaterialPreviewEmbedder(),
            greeting_generator=greeting_generator,
        )
    )
    client.put(
        "/v1/profile",
        json={
            "data": {
                "summary": "熟悉 RAG 与 Agent 开发",
                "defaultGreeting": "您好，我对贵司岗位很感兴趣。",
                "minimumSuitabilityScore": 60,
                "minimumCustomizationConfidence": 1,
            }
        },
    )
    request = {
        "job": {
            "platform": "boss",
            "platformJobId": "atomic-plan-1",
            "url": "https://www.zhipin.com/job_detail/atomic-plan-1.html",
            "title": "AI Agent 工程师",
            "companyName": "示例科技",
            "location": "北京",
            "salaryText": "25-40K",
            "description": "负责 RAG 与 Agent 应用开发",
            "skills": ["Python", "RAG"],
            "capturedAt": "2026-09-30T08:00:00Z",
            "source": "dom",
        }
    }

    response = client.post("/v1/jobs/analyze-and-plan", json=request)

    assert response.status_code == 200
    result = response.json()
    assert result["snapshot"]["platformJobId"] == "atomic-plan-1"
    assert result["match"]["suitabilityScore"] >= 60
    assert result["match"]["decision"]["shouldDeliver"] is True
    assert result["generatedGreeting"].startswith("您好")
    assert client.get("/v1/jobs").json()["total"] == 1


def test_analyze_and_plan_blocks_jobs_below_profile_threshold(tmp_path) -> None:
    class ZeroEmbedder(MaterialPreviewEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0, 0.0] for _text in texts]

    client = TestClient(create_app(tmp_path / "jobs.sqlite3", embedder=ZeroEmbedder()))
    client.put(
        "/v1/profile",
        json={"data": {"minimumSuitabilityScore": 60, "summary": "平面设计"}},
    )
    response = client.post(
        "/v1/jobs/analyze-and-plan",
        json={
            "job": {
                "platform": "boss",
                "platformJobId": "atomic-plan-low",
                "url": "https://www.zhipin.com/job_detail/atomic-plan-low.html",
                "title": "销售经理",
                "companyName": "示例销售公司",
                "description": "负责销售团队管理和业绩目标",
                "capturedAt": "2026-09-30T08:00:00Z",
                "source": "dom",
            }
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["match"]["decision"]["shouldDeliver"] is False
    assert result["match"]["decision"]["materialStrategy"] == "blocked"
    assert result["generatedGreeting"] is None


def test_jd_analysis_returns_evidence_and_default_strategy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    text = "熟悉Python。985、211院校优先。"

    response = client.post("/v1/jd/analyze", json={"jobText": text})

    assert response.status_code == 200
    result = response.json()
    assert result["hasRiskSignals"] is True
    assert result["riskRequirements"][0]["level"] == "preferred"
    evidence = result["riskRequirements"][0]["evidence"]
    assert text[evidence["start"] : evidence["end"]] == evidence["text"]


def test_job_evaluation_applies_user_elite_school_policy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs/evaluate",
        json={
            "jobText": "本科以上学历，985、211院校优先。",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
            "eliteSchoolAction": "use_default_materials",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["hasRiskSignals"] is True
    assert result["decision"]["shouldDeliver"] is True
    assert result["decision"]["materialStrategy"] == "default"


def test_negated_elite_school_text_does_not_apply_policy(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.post(
        "/v1/jobs/evaluate",
        json={
            "jobText": "不要求985、211背景，重视项目能力。",
            "suitabilityScore": 90,
            "customizationConfidence": 90,
            "eliteSchoolAction": "use_default_materials",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["hasRiskSignals"] is False
    assert result["decision"]["materialStrategy"] == "custom"
