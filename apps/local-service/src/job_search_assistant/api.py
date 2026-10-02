import hashlib
import logging
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .domain import (
    DecisionRequest,
    DecisionResponse,
    JdAnalysisRequest,
    JdAnalysisResponse,
    analyze_jd,
    build_automatic_match,
    evaluate_material_strategy,
)
from .domain.models import (
    AutomaticJobMatchRequest,
    AutomaticJobMatchResponse,
    AutomationConfigResponse,
    BrowserProbeRequest,
    BrowserProbeResponse,
    CapturedJob,
    ClientLogInput,
    ClientLogListResponse,
    ClientLogRecord,
    DeliveryListResponse,
    DeliveryRecord,
    DeliveryRecordInput,
    HealthResponse,
    JobAnalysisPlanRequest,
    JobAnalysisPlanResponse,
    JobCaptureRequest,
    JobCaptureResponse,
    JobEvaluationRequest,
    JobEvaluationResponse,
    JobListResponse,
    JobTrackingUpdate,
    LibraryListResponse,
    LibraryRecord,
    LibraryRecordInput,
    ManualJobInput,
    MaterialPreviewRequest,
    MaterialPreviewResponse,
    MaterialStrategy,
    ProfilePayload,
    RagChunkListResponse,
    RagRebuildResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagStatus,
    ResumeConfirmationResponse,
    ResumeImportResponse,
    RiskRuleInput,
    RuleAction,
    SetupCheck,
    SetupStatusResponse,
    SetupTestRunResponse,
    StoredJob,
)
from .project_extraction import (
    GreetingGenerator,
    MaterialPreviewGenerator,
    ModelConnectionTester,
    ProjectExtractor,
)
from .rag import RagService
from .repositories import (
    ClientLogRepository,
    DeliveryRepository,
    JobRepository,
    LibraryRepository,
)
from .repositories.library import ALLOWED_KINDS, LibraryKind
from .resume_html import build_resume_html
from .resume_images import render_pdf_first_page
from .resume_import import MAX_RESUME_BYTES, extract_projects_from_text, parse_resume
from .resume_pdf import build_resume_pdf
from .resume_templates import RESUME_TEMPLATES, SAMPLE_RESUME, TEAL_PROFESSIONAL_ID

logger = logging.getLogger("job_search_assistant.client")
EXPECTED_SKILL_VERSION = "5.10.0"


def create_router(
    job_repository: JobRepository,
    library_repository: LibraryRepository,
    client_log_repository: ClientLogRepository,
    delivery_repository: DeliveryRepository,
    rag_service: RagService,
    project_extractor: ProjectExtractor,
    model_tester: ModelConnectionTester,
    material_preview_generator: MaterialPreviewGenerator,
    greeting_generator: GreetingGenerator,
    resume_image_dir: Path,
) -> APIRouter:
    router = APIRouter(prefix="/v1")
    greeting_generation_ids: set[int] = set()
    greeting_generation_lock = Lock()

    def string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        return [item.strip() for item in re.split(r"[,，|\n;/；]+", str(value)) if item.strip()]

    def matching_rules() -> list[RiskRuleInput]:
        rules: list[RiskRuleInput] = []
        for record in library_repository.list("rules"):
            data = record["data"]
            patterns = string_list(data.get("patterns") or data.get("pattern"))
            if not patterns:
                continue
            try:
                action = RuleAction(str(data.get("action", RuleAction.NOTIFY)))
            except ValueError:
                action = RuleAction.NOTIFY
            rules.append(
                RiskRuleInput(
                    id=f"library:{record['id']}",
                    name=str(record["name"]),
                    patterns=patterns,
                    action=action,
                    score_penalty=int(data.get("scorePenalty", 0) or 0),
                    enabled=bool(data.get("enabled", True)),
                )
            )
        return rules

    def automation_config() -> AutomationConfigResponse:
        profile = library_repository.get_profile()
        target_roles = string_list(profile.get("targetRoles"))
        target_cities = string_list(profile.get("cities"))
        keywords = string_list(profile.get("searchKeywords")) or target_roles
        boss_city_codes = {
            "北京": "101010100",
            "上海": "101020100",
            "广州": "101280100",
            "深圳": "101280600",
            "杭州": "101210100",
        }
        explicit_city_code = str(profile.get("bossCityCode", "")).strip()
        city_code = explicit_city_code or (
            boss_city_codes.get(target_cities[0], "") if target_cities else ""
        )
        try:
            library_repository.get_default_resume_image()
            image_available = True
        except KeyError:
            image_available = False
        return AutomationConfigResponse(
            target_roles=target_roles,
            target_cities=target_cities,
            city_code=city_code,
            search_keywords=keywords,
            minimum_salary_k=int(profile.get("minimumSalaryK", 20) or 20),
            daily_target=int(profile.get("dailyTarget", 20) or 20),
            minimum_suitability_score=int(
                profile.get("minimumSuitabilityScore", 60) or 60
            ),
            minimum_customization_confidence=int(
                profile.get("minimumCustomizationConfidence", 80) or 80
            ),
            send_resume_image=bool(profile.get("sendResumeImage", False)),
            default_greeting=str(profile.get("defaultGreeting", "")).strip(),
            default_resume_image_available=image_available,
            matching_rules=matching_rules(),
        )

    def setup_status() -> SetupStatusResponse:
        config = automation_config()
        models = library_repository.list("models")
        all_resumes = library_repository.list("resumes")
        resumes = [
            record
            for record in all_resumes
            if record["data"].get("confirmationStatus", "confirmed") == "confirmed"
        ]
        pending_resumes = len(all_resumes) - len(resumes)
        rag = rag_service.status()
        checks = [
            SetupCheck(
                key="local-service",
                label="本地服务",
                status="ready",
                message=f"本地 API v{__version__} 已运行",
            )
        ]

        if rag["embeddingAvailable"]:
            checks.append(
                SetupCheck(
                    key="embedding",
                    label="向量服务",
                    status="ready",
                    message=f"向量模型 {rag.get('model') or '已连接'} 可用",
                )
            )
        else:
            checks.append(
                SetupCheck(
                    key="embedding",
                    label="向量服务",
                    status="blocked",
                    message="向量服务未就绪，请检查 Docker 服务",
                    blocking=True,
                    action_label="查看安装说明",
                    action_path="/setup#services",
                )
            )

        verified_models = [
            record
            for record in models
            if record["data"].get("lastVerificationStatus") == "ok"
        ]
        if verified_models:
            checks.append(
                SetupCheck(
                    key="model",
                    label="大模型连接",
                    status="ready",
                    message=f"已验证 {len(verified_models)} 个模型配置",
                    action_label="管理模型",
                    action_path="/models",
                )
            )
        elif models:
            checks.append(
                SetupCheck(
                    key="model",
                    label="大模型连接",
                    status="warning",
                    message="模型已配置，但还没有通过连接测试",
                    blocking=True,
                    action_label="测试模型",
                    action_path="/models",
                )
            )
        else:
            checks.append(
                SetupCheck(
                    key="model",
                    label="大模型连接",
                    status="blocked",
                    message="尚未配置用于简历识别与材料生成的模型",
                    blocking=True,
                    action_label="配置模型",
                    action_path="/models",
                )
            )

        checks.append(
            SetupCheck(
                key="resume",
                label="简历资料",
                status="ready" if resumes else "blocked",
                message=(
                    f"已导入 {len(resumes)} 份简历"
                    if resumes
                    else (
                        f"有 {pending_resumes} 份简历等待确认"
                        if pending_resumes
                        else "尚未导入简历"
                    )
                ),
                blocking=not resumes,
                action_label="管理简历" if resumes else "导入简历",
                action_path="/resumes",
            )
        )

        indexed_chunks = int(rag.get("chunks", 0) or 0)
        checks.append(
            SetupCheck(
                key="knowledge-index",
                label="知识索引",
                status="ready" if indexed_chunks else "blocked",
                message=(
                    f"已建立 {indexed_chunks} 个知识片段"
                    if indexed_chunks
                    else "知识索引为空，请导入简历或重建索引"
                ),
                blocking=not indexed_chunks,
                action_label="查看知识库",
                action_path="/knowledge",
            )
        )

        missing_config: list[str] = []
        if not config.target_roles:
            missing_config.append("目标岗位")
        if not config.city_code:
            missing_config.append("投递城市")
        if not config.search_keywords:
            missing_config.append("搜索关键词")
        if not config.default_greeting:
            missing_config.append("默认招呼语")
        checks.append(
            SetupCheck(
                key="delivery-config",
                label="投递偏好",
                status="ready" if not missing_config else "blocked",
                message=(
                    "目标岗位、城市、关键词与招呼语已配置"
                    if not missing_config
                    else f"还需配置：{'、'.join(missing_config)}"
                ),
                blocking=bool(missing_config),
                action_label="完善个人资料",
                action_path="/profile",
            )
        )

        image_missing = config.send_resume_image and not config.default_resume_image_available
        checks.append(
            SetupCheck(
                key="resume-image",
                label="简历图片",
                status="blocked" if image_missing else "ready",
                message=(
                    "已启用图片发送，但没有可用的默认简历图片"
                    if image_missing
                    else (
                        "默认简历图片可用"
                        if config.default_resume_image_available
                        else "未启用简历图片发送，可稍后配置"
                    )
                ),
                blocking=image_missing,
                action_label="管理简历",
                action_path="/resumes",
            )
        )

        browser_probe = library_repository.get_setup_state("browser-probe")
        probe_fresh = False
        if browser_probe and browser_probe.get("checkedAt"):
            checked_at = datetime.fromisoformat(str(browser_probe["checkedAt"]))
            probe_fresh = (datetime.now(UTC) - checked_at).total_seconds() <= 12 * 60 * 60
        if not probe_fresh:
            browser_probe = None

        webbridge_ready = bool(
            browser_probe
            and browser_probe.get("webbridgeRunning")
            and browser_probe.get("kimiExtensionConnected")
        )
        checks.append(
            SetupCheck(
                key="kimi-webbridge",
                label="Kimi WebBridge",
                status="ready" if webbridge_ready else ("blocked" if browser_probe else "pending"),
                message=(
                    "WebBridge 正在运行，Kimi 浏览器扩展已连接"
                    if webbridge_ready
                    else (
                        "WebBridge 或 Kimi 浏览器扩展未连接"
                        if browser_probe
                        else "尚未检查 Kimi WebBridge"
                    )
                ),
                blocking=not webbridge_ready,
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )

        project_extension_ready = bool(
            browser_probe and browser_probe.get("projectExtensionReady")
        )
        extension_required = config.send_resume_image
        checks.append(
            SetupCheck(
                key="project-extension",
                label="简历图片扩展",
                status=(
                    "ready"
                    if project_extension_ready
                    else ("blocked" if extension_required and browser_probe else "warning")
                ),
                message=(
                    "项目扩展已在 BOSS 页面显示操作面板"
                    if project_extension_ready
                    else (
                        "已开启简历图片发送，必须确认项目扩展可用"
                        if extension_required
                        else "未启用图片发送，可稍后确认项目扩展"
                    )
                ),
                blocking=extension_required and not project_extension_ready,
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )

        boss_logged_in = bool(browser_probe and browser_probe.get("bossLoggedIn"))
        checks.append(
            SetupCheck(
                key="boss-login",
                label="BOSS 登录",
                status="ready" if boss_logged_in else ("blocked" if browser_probe else "pending"),
                message=(
                    "已确认 BOSS 账号处于登录状态"
                    if boss_logged_in
                    else ("BOSS 登录状态未通过确认" if browser_probe else "尚未确认 BOSS 登录状态")
                ),
                blocking=not boss_logged_in,
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )

        skill_version = str(browser_probe.get("skillVersion", "")) if browser_probe else ""
        skill_ready = skill_version == EXPECTED_SKILL_VERSION
        checks.append(
            SetupCheck(
                key="skill-version",
                label="BOSS Skill",
                status="ready" if skill_ready else ("blocked" if skill_version else "pending"),
                message=(
                    f"BOSS Skill v{EXPECTED_SKILL_VERSION} 已安装"
                    if skill_ready
                    else (
                        f"需要 v{EXPECTED_SKILL_VERSION}，当前为 v{skill_version}"
                        if skill_version
                        else "尚未确认 BOSS Skill 版本"
                    )
                ),
                blocking=not skill_ready,
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )
        priority = {"ready": 0, "warning": 1, "pending": 2, "blocked": 3}
        overall = max((check.status for check in checks), key=priority.__getitem__)
        return SetupStatusResponse(
            overall=overall,
            completed=sum(check.status == "ready" for check in checks),
            total=len(checks),
            checks=checks,
            checked_at=datetime.now(UTC),
        )

    def validate_model_data(data: dict[str, object]) -> None:
        missing = [field for field in ("modelId", "apiKey", "baseUrl") if not data.get(field)]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"model configuration missing: {', '.join(missing)}",
            )

    def public_model_record(record: dict[str, object]) -> LibraryRecord:
        safe_record = {**record, "data": dict(record["data"])}
        data = safe_record["data"]
        api_key = str(data.pop("apiKey", ""))
        data["apiKeyConfigured"] = bool(api_key)
        data["apiKeyHint"] = f"••••{api_key[-4:]}" if api_key else ""
        return LibraryRecord.model_validate(safe_record)

    def sync_knowledge_index() -> None:
        """Best-effort automatic entity index sync; data writes remain available offline."""
        try:
            rag_service.rebuild()
        except RuntimeError as error:
            logger.warning("knowledge index sync skipped: %s", error)

    def build_job_material_context(
        job: StoredJob,
        *,
        minimum_suitability_score: int = 75,
        minimum_customization_confidence: int = 80,
        rules: list[RiskRuleInput] | None = None,
        duplicate: bool = False,
        company_blocked: bool = False,
    ) -> tuple[dict[str, object], str, AutomaticJobMatchResponse]:
        match_request = AutomaticJobMatchRequest(
            title=job.title,
            job_text=job.description,
            skills=job.skills,
            minimum_suitability_score=minimum_suitability_score,
            minimum_customization_confidence=minimum_customization_confidence,
            rules=rules or [],
            duplicate=duplicate,
            company_blocked=company_blocked,
        )
        query = "\n".join(
            part for part in [job.title, " ".join(job.skills), job.description] if part
        )
        try:
            evidence = rag_service.search(query, 8)
        except RuntimeError as error:
            logger.warning(
                "greeting vector evidence unavailable for job=%s: %s", job.id, error
            )
            evidence = []
        match = build_automatic_match(match_request, evidence)
        profile = library_repository.get_profile()
        resumes = [
            record
            for record in library_repository.list("resumes")
            if record["data"].get("confirmationStatus", "confirmed") == "confirmed"
        ]
        default_greeting = str(profile.get("defaultGreeting", "")).strip()
        context = {
            "job": job.model_dump(mode="json", by_alias=True),
            "profile": profile,
            "vectorEvidence": [
                item.model_dump(mode="json", by_alias=True) for item in match.evidence
            ],
            "defaultGreeting": default_greeting,
            "defaultResume": resumes[0]["data"] if resumes else {},
            "match": {
                "suitabilityScore": match.suitability_score,
                "customizationConfidence": match.customization_confidence,
                "materialStrategy": match.decision.material_strategy,
            },
        }
        return context, default_greeting, match

    def generate_and_store_greeting(snapshot_id: int) -> None:
        try:
            job = job_repository.get(snapshot_id)
            if job.generated_greeting:
                return
            context, default_greeting, _ = build_job_material_context(job)
            try:
                greeting_context = {
                    key: context[key]
                    for key in (
                        "job",
                        "profile",
                        "vectorEvidence",
                        "defaultGreeting",
                        "match",
                    )
                }
                generated = greeting_generator.generate(greeting_context)
                greeting = str(generated["greeting"]).strip()
            except (RuntimeError, KeyError, TypeError) as error:
                greeting = default_greeting or (
                    f"您好，我对贵司的{job.title}岗位很感兴趣，"
                    "希望有机会进一步沟通，谢谢。"
                )
                logger.warning(
                    "automatic greeting generation fell back for job=%s: %s",
                    snapshot_id,
                    error,
                )
            job_repository.update_generated_greeting(snapshot_id, greeting)
        except KeyError:
            logger.warning("automatic greeting skipped: job=%s no longer exists", snapshot_id)
        except Exception:
            logger.exception("automatic greeting failed unexpectedly for job=%s", snapshot_id)

    def run_greeting_task(snapshot_id: int) -> None:
        try:
            generate_and_store_greeting(snapshot_id)
        finally:
            with greeting_generation_lock:
                greeting_generation_ids.discard(snapshot_id)

    def queue_greeting_generation(
        snapshot_id: int, background_tasks: BackgroundTasks
    ) -> None:
        with greeting_generation_lock:
            if snapshot_id in greeting_generation_ids:
                return
            greeting_generation_ids.add(snapshot_id)
        background_tasks.add_task(run_greeting_task, snapshot_id)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @router.get("/automation/config", response_model=AutomationConfigResponse)
    def get_automation_config() -> AutomationConfigResponse:
        return automation_config()

    @router.get("/setup/status", response_model=SetupStatusResponse)
    def get_setup_status() -> SetupStatusResponse:
        return setup_status()

    @router.post("/setup/browser/probe", response_model=BrowserProbeResponse)
    def save_browser_probe(request: BrowserProbeRequest) -> BrowserProbeResponse:
        state = library_repository.save_setup_state(
            "browser-probe", request.model_dump(mode="json", by_alias=True)
        )
        return BrowserProbeResponse.model_validate(state)

    @router.post("/setup/test-run", response_model=SetupTestRunResponse)
    def run_setup_test() -> SetupTestRunResponse:
        status_result = setup_status()
        blocking_checks = [
            check.label
            for check in status_result.checks
            if check.blocking and check.status != "ready"
        ]
        config = automation_config()
        ok = not blocking_checks
        return SetupTestRunResponse(
            ok=ok,
            planned_keywords=config.search_keywords,
            daily_target=config.daily_target,
            blocking_checks=blocking_checks,
            message=(
                "安全测试通过；未打开 BOSS 页面，也未执行点击、发送或投递"
                if ok
                else f"安全测试未通过，请先处理：{'、'.join(blocking_checks)}"
            ),
        )

    @router.post("/client-logs", response_model=ClientLogRecord, status_code=201)
    def create_client_log(request: ClientLogInput) -> ClientLogRecord:
        record = ClientLogRecord.model_validate(
            client_log_repository.create(request.model_dump(by_alias=False))
        )
        logger.log(
            logging.ERROR if request.level == "error" else logging.WARNING,
            "client event=%s source=%s job=%s message=%s",
            request.event,
            request.source,
            request.platform_job_id or "-",
            request.message,
        )
        return record

    @router.get("/client-logs", response_model=ClientLogListResponse)
    def list_client_logs(limit: int = Query(default=100, ge=1, le=500)) -> ClientLogListResponse:
        return ClientLogListResponse(items=client_log_repository.list_recent(limit))

    @router.post("/deliveries", response_model=DeliveryRecord, status_code=201)
    def save_delivery(request: DeliveryRecordInput) -> DeliveryRecord:
        return delivery_repository.upsert(request)

    @router.get("/deliveries", response_model=DeliveryListResponse)
    def list_deliveries(limit: int = Query(default=100, ge=1, le=500)) -> DeliveryListResponse:
        return DeliveryListResponse(
            total=delivery_repository.count(),
            items=delivery_repository.list_recent(limit),
        )

    @router.post("/decisions/evaluate", response_model=DecisionResponse)
    def evaluate_decision(request: DecisionRequest) -> DecisionResponse:
        return evaluate_material_strategy(request)

    @router.post("/jobs/capture", response_model=JobCaptureResponse)
    def capture_jobs(
        request: JobCaptureRequest, background_tasks: BackgroundTasks
    ) -> JobCaptureResponse:
        job_ids = job_repository.save_many(request.jobs)
        for captured in request.jobs:
            try:
                stored = job_repository.get_by_platform_job_id(
                    captured.platform, captured.platform_job_id
                )
            except KeyError:
                continue
            if not stored.generated_greeting:
                queue_greeting_generation(stored.id, background_tasks)
        return JobCaptureResponse(accepted=len(job_ids), job_ids=job_ids)

    @router.get("/jobs", response_model=JobListResponse)
    def list_jobs(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
        query: str | None = Query(default=None, max_length=300),
        communication_result: Literal[
            "not_communicated", "communicated", "interviewed"
        ] | None = Query(default=None, alias="communicationResult"),
    ) -> JobListResponse:
        total = job_repository.count(query, communication_result)
        total_pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        return JobListResponse(
            total=total,
            page=current_page,
            page_size=page_size,
            total_pages=total_pages,
            items=job_repository.list_recent(
                page_size,
                offset=(current_page - 1) * page_size,
                query=query,
                communication_result=communication_result,
            ),
        )

    @router.post("/jobs", response_model=StoredJob, status_code=201)
    def create_job(request: ManualJobInput, background_tasks: BackgroundTasks) -> StoredJob:
        job = CapturedJob(
            platform="boss",
            platform_job_id=f"manual-{uuid4().hex}",
            url=request.url or "https://www.zhipin.com/",
            title=request.title,
            company_name=request.company_name,
            company_size=request.company_size,
            location=request.location,
            work_address=request.work_address,
            salary_text=request.salary_text,
            experience=request.experience,
            education=request.education,
            description=request.description,
            skills=request.skills,
            recruiter_name=request.recruiter_name,
            recruiter_title=request.recruiter_title,
            has_communicated=request.has_communicated,
            has_interview=request.has_interview,
            generated_greeting=request.generated_greeting,
            resume_variant=request.resume_variant,
            generated_resume_id=request.generated_resume_id,
            resume_optimization=request.resume_optimization,
            captured_at=datetime.now(UTC),
            source="manual",
        )
        stored = job_repository.create(job)
        if not stored.generated_greeting:
            queue_greeting_generation(stored.id, background_tasks)
        return stored

    @router.put("/jobs/{snapshot_id}/tracking", response_model=StoredJob)
    def update_job_tracking(snapshot_id: int, request: JobTrackingUpdate) -> StoredJob:
        try:
            return job_repository.update_tracking(
                snapshot_id, request.model_dump(by_alias=False)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job snapshot not found") from error

    @router.delete("/jobs/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_job(snapshot_id: int) -> Response:
        if not job_repository.delete(snapshot_id):
            raise HTTPException(status_code=404, detail="job snapshot not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/jd/analyze", response_model=JdAnalysisResponse)
    def analyze_job_description(request: JdAnalysisRequest) -> JdAnalysisResponse:
        return analyze_jd(request.job_text)

    @router.post("/jobs/evaluate", response_model=JobEvaluationResponse)
    def evaluate_job(request: JobEvaluationRequest) -> JobEvaluationResponse:
        analysis = analyze_jd(request.job_text)
        rules = list(request.rules)
        if analysis.risk_requirements:
            patterns = sorted(
                {
                    pattern
                    for requirement in analysis.risk_requirements
                    for pattern in requirement.normalized_value.split("|")
                }
            )
            rules.append(
                RiskRuleInput(
                    id="builtin:elite-school",
                    name="名校学历偏好",
                    patterns=patterns,
                    action=request.elite_school_action,
                )
            )
        decision = evaluate_material_strategy(
            DecisionRequest(
                job_text=request.job_text,
                suitability_score=request.suitability_score,
                customization_confidence=request.customization_confidence,
                minimum_suitability_score=request.minimum_suitability_score,
                minimum_customization_confidence=request.minimum_customization_confidence,
                rules=rules,
                duplicate=request.duplicate,
                company_blocked=request.company_blocked,
            )
        )
        return JobEvaluationResponse(analysis=analysis, decision=decision)

    @router.post("/jobs/match", response_model=AutomaticJobMatchResponse)
    def match_job(request: AutomaticJobMatchRequest) -> AutomaticJobMatchResponse:
        query = "\n".join(
            part for part in [request.title, " ".join(request.skills), request.job_text] if part
        )
        try:
            evidence = rag_service.search(query, 8)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return build_automatic_match(request, evidence)

    @router.post("/jobs/analyze-and-plan", response_model=JobAnalysisPlanResponse)
    def analyze_and_plan_job(request: JobAnalysisPlanRequest) -> JobAnalysisPlanResponse:
        job_repository.save_many([request.job])
        job = job_repository.get_by_platform_job_id(
            request.job.platform, request.job.platform_job_id
        )
        config = automation_config()
        suitability_threshold = (
            request.minimum_suitability_score
            if request.minimum_suitability_score is not None
            else config.minimum_suitability_score
        )
        confidence_threshold = (
            request.minimum_customization_confidence
            if request.minimum_customization_confidence is not None
            else config.minimum_customization_confidence
        )
        context, default_greeting, match = build_job_material_context(
            job,
            minimum_suitability_score=suitability_threshold,
            minimum_customization_confidence=confidence_threshold,
            rules=config.matching_rules,
            duplicate=job.has_communicated,
            company_blocked=request.company_blocked,
        )

        # 适合度是是否投递的硬门槛；定制可信度不足时才回退默认材料。
        if match.suitability_score < suitability_threshold:
            match = match.model_copy(
                update={
                    "decision": match.decision.model_copy(
                        update={
                            "material_strategy": MaterialStrategy.BLOCKED,
                            "should_deliver": False,
                            "reasons": [
                                "岗位适合度 "
                                f"{match.suitability_score} 低于投递阈值 "
                                f"{suitability_threshold}"
                            ],
                        }
                    )
                }
            )

        greeting: str | None = job.generated_greeting
        if match.decision.should_deliver and not greeting:
            if match.decision.material_strategy == "custom":
                try:
                    generated = greeting_generator.generate(
                        {
                            key: context[key]
                            for key in (
                                "job",
                                "profile",
                                "vectorEvidence",
                                "defaultGreeting",
                                "match",
                            )
                        }
                    )
                    greeting = str(generated["greeting"]).strip()
                except (RuntimeError, KeyError, TypeError) as error:
                    logger.warning("planned greeting fell back for job=%s: %s", job.id, error)
            greeting = greeting or default_greeting or (
                f"您好，我对贵司的{job.title}岗位很感兴趣，希望有机会进一步沟通，谢谢。"
            )
            job = job_repository.update_generated_greeting(job.id, greeting)

        return JobAnalysisPlanResponse(
            snapshot=job,
            match=match,
            generated_greeting=greeting,
            default_resume_image_available=config.default_resume_image_available,
            duplicate=job.has_communicated,
        )

    @router.post(
        "/jobs/{snapshot_id}/material-preview",
        response_model=MaterialPreviewResponse,
    )
    def preview_job_materials(
        snapshot_id: int, request: MaterialPreviewRequest
    ) -> MaterialPreviewResponse:
        try:
            job = job_repository.get(snapshot_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job snapshot not found") from error
        try:
            context, default_greeting, match = build_job_material_context(job)
            generated = material_preview_generator.generate(
                context,
                request.model_record_id,
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return MaterialPreviewResponse(
            job_id=job.id,
            model_record_id=int(generated["modelRecordId"]),
            model_name=str(generated["modelName"]),
            model_id=str(generated["modelId"]),
            default_greeting=default_greeting,
            greeting=str(generated["greeting"]),
            resume=generated["resume"],
            match=match,
        )

    @router.get("/profile", response_model=ProfilePayload)
    def get_profile() -> ProfilePayload:
        return ProfilePayload(data=library_repository.get_profile())

    @router.put("/profile", response_model=ProfilePayload)
    def save_profile(request: ProfilePayload) -> ProfilePayload:
        profile = library_repository.save_profile(request.data)
        sync_knowledge_index()
        return ProfilePayload(data=profile)

    @router.post("/resumes/import", response_model=ResumeImportResponse, status_code=201)
    async def import_resume(
        file: Annotated[UploadFile, File()],
        model_record_id: Annotated[int | None, Form(alias="modelRecordId")] = None,
    ) -> ResumeImportResponse:
        filename = Path((file.filename or "resume").replace("\\", "/")).name
        try:
            file_content = await file.read(MAX_RESUME_BYTES + 1)
            parsed = parse_resume(filename, file_content)
            if Path(filename).suffix.lower() == ".pdf":
                preview_path = await run_in_threadpool(
                    render_pdf_first_page, file_content, resume_image_dir
                )
                parsed.resume["previewImageFile"] = preview_path.name
            ai_extraction_used = False
            ai_extraction_error = None
            ai_attempt_errors: list[str] = []
            ai_profile_extracted = False
            projects = parsed.projects
            ai_model_record = None
            profile = parsed.profile
            try:
                extract_resume = getattr(project_extractor, "extract_resume", None)
                if callable(extract_resume):
                    extraction = await run_in_threadpool(
                        extract_resume, parsed.resume["rawText"], model_record_id
                    )
                    extracted_projects = list(extraction.get("projects", []))
                    extracted_profile = dict(extraction.get("profile", {}))
                    profile = {**parsed.profile, **extracted_profile}
                    ai_profile_extracted = bool(extracted_profile)
                    ai_attempt_errors = list(extraction.get("attemptErrors", []))
                    ai_model_record = {
                        "id": extraction.get("modelRecordId"),
                        "name": extraction.get("modelName"),
                        "data": {"modelId": extraction.get("modelId")},
                    }
                    ai_extraction_used = bool(extracted_profile or extracted_projects)
                else:
                    extracted_projects = await run_in_threadpool(
                        project_extractor.extract, parsed.resume["rawText"], model_record_id
                    )
                if extracted_projects:
                    projects = extracted_projects
                    ai_extraction_used = True
                elif not ai_profile_extracted:
                    ai_extraction_error = "模型未识别到项目，已使用本地项目标题规则降级解析"
                if ai_model_record is None:
                    models = library_repository.list("models")
                    if model_record_id is not None:
                        ai_model_record = next(
                            (record for record in models if record["id"] == model_record_id), None
                        )
                    elif models:
                        ai_model_record = next(
                            (
                                record
                                for record in models
                                if record["data"].get("usageRole") == "primary"
                            ),
                            models[0],
                        )
            except RuntimeError as error:
                ai_extraction_error = str(error)
            for project in projects:
                source_key = hashlib.sha256(
                    f"{parsed.resume['sourceHash']}:{project['name'].strip().lower()}".encode()
                ).hexdigest()
                project["data"] = {
                    **project.get("data", {}),
                    "source": "resume-import",
                    "sourceFile": filename,
                    "sourceHash": parsed.resume["sourceHash"],
                    "sourceKey": source_key,
                }
            imported = library_repository.import_resume(
                filename, profile, parsed.resume, projects
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return ResumeImportResponse(
            filename=filename,
            profile_fields=sorted(imported["profile"]),
            resume_id=imported["resumeId"],
            project_ids=imported["projectIds"],
            extracted_characters=len(parsed.resume["rawText"]),
            index_rebuilt=False,
            indexed_chunks=None,
            index_error=None,
            ai_extraction_used=ai_extraction_used,
            ai_project_count=len(projects) if ai_extraction_used else 0,
            ai_extraction_error=ai_extraction_error,
            ai_model_record_id=ai_model_record["id"] if ai_model_record else None,
            ai_model_name=ai_model_record["name"] if ai_model_record else None,
            ai_model_id=(
                str(ai_model_record["data"].get("modelId", "")) if ai_model_record else None
            ),
            ai_attempt_errors=ai_attempt_errors,
            ai_profile_extracted=ai_profile_extracted,
        )

    @router.post(
        "/resumes/{resume_id}/confirm",
        response_model=ResumeConfirmationResponse,
    )
    def confirm_resume(resume_id: int) -> ResumeConfirmationResponse:
        try:
            confirmed = library_repository.confirm_resume(resume_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        rebuilt = False
        indexed_chunks = None
        index_error = None
        try:
            index_result = rag_service.rebuild()
            rebuilt = True
            indexed_chunks = index_result["rebuilt"]
        except RuntimeError as error:
            index_error = str(error)
        return ResumeConfirmationResponse(
            resume=LibraryRecord.model_validate(confirmed["resume"]),
            profile_fields=sorted(confirmed["profile"]),
            project_ids=confirmed["projectIds"],
            index_rebuilt=rebuilt,
            indexed_chunks=indexed_chunks,
            index_error=index_error,
        )

    def resume_image_response(record: dict[str, object]) -> FileResponse:
        data = dict(record["data"])
        image_name = Path(str(data.get("previewImageFile", ""))).name
        image_path = resume_image_dir / image_name
        if not image_name or not image_path.is_file():
            raise HTTPException(status_code=404, detail="resume image not found")
        return FileResponse(
            image_path,
            media_type="image/png",
            filename=f"resume-{record['id']}-page-1.png",
        )

    @router.get("/resumes/default-image")
    def get_default_resume_image() -> FileResponse:
        try:
            return resume_image_response(library_repository.get_default_resume_image())
        except KeyError as error:
            raise HTTPException(status_code=404, detail="default resume image not found") from error

    @router.get("/resumes/{resume_id}/preview-image")
    def get_resume_preview_image(resume_id: int) -> FileResponse:
        try:
            record = library_repository.get("resumes", resume_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        return resume_image_response(record)

    @router.put("/resumes/{resume_id}/default-image", response_model=LibraryRecord)
    def set_default_resume_image(resume_id: int) -> LibraryRecord:
        try:
            return LibraryRecord(**library_repository.set_default_resume_image(resume_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/resumes/{resume_id}/extract-projects")
    async def extract_existing_resume_projects(
        resume_id: int,
        model_record_id: Annotated[int | None, Form(alias="modelRecordId")] = None,
    ) -> dict[str, object]:
        try:
            resume_record = library_repository.get("resumes", resume_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        resume = resume_record["data"]
        raw_text = str(resume.get("rawText", "")).strip()
        if not raw_text:
            raise HTTPException(status_code=422, detail="简历记录没有可供识别的原文")
        filename = str(resume.get("fileName") or resume_record["name"])
        source_hash = str(resume.get("sourceHash", ""))
        extraction_method = "ai"
        extraction_error = None
        try:
            projects = await run_in_threadpool(
                project_extractor.extract, raw_text, model_record_id
            )
        except RuntimeError as error:
            projects = []
            extraction_error = str(error)
        if not projects:
            projects = extract_projects_from_text(raw_text, source_hash, filename)
            extraction_method = "local-heading-fallback"
        if not projects:
            raise HTTPException(
                status_code=422,
                detail=extraction_error or "没有从这份简历中识别到独立项目",
            )
        for project in projects:
            source_key = hashlib.sha256(
                f"{source_hash}:{project['name'].strip().lower()}".encode()
            ).hexdigest()
            project["data"] = {
                **project.get("data", {}),
                "source": "resume-import",
                "sourceResumeId": resume_id,
                "sourceFile": filename,
                "sourceHash": source_hash,
                "sourceKey": source_key,
            }
        project_ids = library_repository.upsert_projects(projects)
        try:
            index_result = rag_service.rebuild()
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail=f"项目已入库，但向量索引失败: {error}",
            ) from error
        return {
            "resumeId": resume_id,
            "projectIds": project_ids,
            "projectCount": len(project_ids),
            "extractionMethod": extraction_method,
            "extractionError": extraction_error,
            "indexedChunks": index_result["rebuilt"],
        }

    def valid_kind(kind: str) -> LibraryKind:
        if kind not in ALLOWED_KINDS:
            raise HTTPException(status_code=404, detail="library kind not found")
        return kind  # type: ignore[return-value]

    @router.get("/library/{kind}", response_model=LibraryListResponse)
    def list_library(kind: str) -> LibraryListResponse:
        valid = valid_kind(kind)
        records = library_repository.list(valid)
        if valid == "models":
            return LibraryListResponse(items=[public_model_record(record) for record in records])
        return LibraryListResponse(items=records)

    @router.post("/library/{kind}", response_model=LibraryRecord, status_code=201)
    def create_library_record(kind: str, request: LibraryRecordInput) -> LibraryRecord:
        valid = valid_kind(kind)
        if valid == "models":
            validate_model_data(request.data)
            return public_model_record(library_repository.create(valid, request.name, request.data))
        record = LibraryRecord.model_validate(
            library_repository.create(valid, request.name, request.data)
        )
        if valid == "projects":
            sync_knowledge_index()
        return record

    @router.put("/library/{kind}/{record_id}", response_model=LibraryRecord)
    def update_library_record(
        kind: str, record_id: int, request: LibraryRecordInput
    ) -> LibraryRecord:
        try:
            valid = valid_kind(kind)
            data = request.data
            if valid == "models":
                existing = library_repository.get(valid, record_id)
                data = {**existing["data"], **request.data}
                data.pop("apiKeyConfigured", None)
                data.pop("apiKeyHint", None)
                connection_fields = ("provider", "modelId", "baseUrl", "apiKey")
                if any(
                    field in request.data
                    and request.data[field] != existing["data"].get(field)
                    for field in connection_fields
                ):
                    data.pop("lastVerificationStatus", None)
                    data.pop("lastVerifiedAt", None)
                    data.pop("lastVerifiedLatencyMs", None)
                validate_model_data(data)
            result = library_repository.update(valid, record_id, request.name, data)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="record not found") from error
        if valid == "models":
            return public_model_record(result)
        record = LibraryRecord.model_validate(result)
        if valid == "projects":
            sync_knowledge_index()
        return record

    @router.delete("/library/{kind}/{record_id}", status_code=204)
    def delete_library_record(kind: str, record_id: int) -> Response:
        valid = valid_kind(kind)
        if not library_repository.delete(valid, record_id):
            raise HTTPException(status_code=404, detail="record not found")
        if valid == "projects":
            sync_knowledge_index()
        return Response(status_code=204)

    @router.post("/library/models/{record_id}/test")
    def test_model_connection(record_id: int) -> dict[str, object]:
        try:
            record = library_repository.get("models", record_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="model configuration not found") from error
        try:
            result = model_tester.test(record["data"])
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        data = {
            **record["data"],
            "lastVerificationStatus": "ok",
            "lastVerifiedAt": datetime.now(UTC).isoformat(),
            "lastVerifiedLatencyMs": result.get("latencyMs"),
        }
        library_repository.update("models", record_id, record["name"], data)
        return result

    @router.get("/rag/status", response_model=RagStatus)
    def rag_status() -> RagStatus:
        return RagStatus.model_validate(rag_service.status())

    @router.get("/rag/chunks", response_model=RagChunkListResponse)
    def list_rag_chunks() -> RagChunkListResponse:
        items = rag_service.list_chunks()
        return RagChunkListResponse(total=len(items), items=items)

    @router.delete("/rag/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_rag_chunk(chunk_id: int) -> Response:
        if not rag_service.delete_chunk(chunk_id):
            raise HTTPException(status_code=404, detail="knowledge entity not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/rag/rebuild", response_model=RagRebuildResponse)
    def rebuild_rag_index() -> RagRebuildResponse:
        try:
            return RagRebuildResponse.model_validate(rag_service.rebuild())
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.post("/rag/search", response_model=RagSearchResponse)
    def search_rag(request: RagSearchRequest) -> RagSearchResponse:
        try:
            return RagSearchResponse(items=rag_service.search(request.query, request.limit))
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/resume-templates")
    def list_resume_templates() -> dict[str, object]:
        return {"items": RESUME_TEMPLATES, "sampleData": SAMPLE_RESUME}

    @router.get("/resume-templates/{template_id}/sample", response_class=HTMLResponse)
    def preview_sample_resume(template_id: str) -> HTMLResponse:
        if template_id != TEAL_PROFESSIONAL_ID:
            raise HTTPException(status_code=404, detail="resume template not found")
        return HTMLResponse(build_resume_html(SAMPLE_RESUME), headers={"Cache-Control": "no-store"})

    @router.get("/resume-templates/{template_id}/sample.pdf")
    def download_sample_resume(template_id: str) -> StreamingResponse:
        if template_id != TEAL_PROFESSIONAL_ID:
            raise HTTPException(status_code=404, detail="resume template not found")
        pdf = build_resume_pdf(SAMPLE_RESUME)
        return StreamingResponse(
            BytesIO(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    'inline; filename="job-search-assistant-sample-resume.pdf"'
                ),
                "Cache-Control": "no-store",
            },
        )

    return router
