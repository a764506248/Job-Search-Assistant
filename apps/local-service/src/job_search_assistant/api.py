import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .auth_token import issue_token, verify_token
from .config import settings
from .automation.browser_protocol import (
    ALLOWED_ACTIONS,
    PROTOCOL_VERSION,
    BrowserConnectionHub,
    BrowserProtocolError,
)
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
    AutomationActionClaimRequest,
    AutomationActionClaimResponse,
    AutomationActionResultRequest,
    AutomationBrowserActionRequest,
    AutomationBrowserActionResponse,
    AutomationConfigResponse,
    AutomationEventListResponse,
    AutomationHeartbeatRequest,
    AutomationProgressRequest,
    AutomationReport,
    AutomationRun,
    AutomationRunCreateRequest,
    AutomationRunListResponse,
    AutomationRunnerClaimResponse,
    AutomationRunnerFinishRequest,
    AutomationRunnerStatus,
    AutomationRunStartRequest,
    BrowserActionResponse,
    BrowserPairingResponse,
    BrowserProbeRequest,
    BrowserProbeResponse,
    BrowserProtocolStatus,
    BrowserTestActionRequest,
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
    JobInsightRequest,
    JobInsightResponse,
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
    ResumeConfirmationResponse,
    ResumeImportResponse,
    RiskRuleInput,
    RuleAction,
    RuleMatch,
    SetupCheck,
    SetupStatusResponse,
    SetupTestRunResponse,
    StoredJob,
)
from .domain.salary import evaluate_salary_policy, normalize_salary_text
from .knowledge import KnowledgeSearchService
from .project_extraction import (
    GreetingGenerator,
    JobAnalysisGenerator,
    MaterialPreviewGenerator,
    ModelConnectionTester,
    ProjectExtractor,
)
from .repositories import (
    AutomationRepository,
    AuthRepository,
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
MIN_COLLECTION_EXTENSION_VERSION = (0, 4, 11)
COLLECTION_BATCH_SIZE = 10
COLLECTION_BATCH_DEADLINE_MS = 30_000
MAX_COLLECTION_BATCH_DEADLINE_MS = 330_000
COLLECTION_FILTER_KEYS = (
    "jobType",
    "salary",
    "experience",
    "degree",
    "industry",
    "scale",
)


def extension_supports_collection(version: object) -> bool:
    parts = [int(value) for value in re.findall(r"\d+", str(version))[:3]]
    parts.extend([0] * (3 - len(parts)))
    return tuple(parts) >= MIN_COLLECTION_EXTENSION_VERSION


def browser_protocol_error_message(error: BrowserProtocolError, action: str) -> str:
    message = str(error)
    if "browser action timed out" in message:
        if action == "collect_jobs":
            return "扩展采集单批职位超时，请适当降低岗位采集间隔"
        labels = {
            "session_status": "检查 BOSS 登录状态",
            "navigate_search": "打开 BOSS 搜索页",
        }
        return f"{labels.get(action, '浏览器操作')}超时（30 秒）"
    if "browser extension disconnected" in message:
        return "统一 Chrome 扩展连接已断开"
    if "browser extension is not connected" in message:
        return "统一 Chrome 扩展未连接"
    return message


def create_router(
    job_repository: JobRepository,
    library_repository: LibraryRepository,
    client_log_repository: ClientLogRepository,
    delivery_repository: DeliveryRepository,
    knowledge_search: KnowledgeSearchService,
    project_extractor: ProjectExtractor,
    model_tester: ModelConnectionTester,
    material_preview_generator: MaterialPreviewGenerator,
    greeting_generator: GreetingGenerator,
    job_analysis_generator: JobAnalysisGenerator,
    resume_image_dir: Path,
    automation_repository: AutomationRepository,
    browser_hub: BrowserConnectionHub,
    auth_repository: AuthRepository | None = None,
) -> APIRouter:
    auth_repository = auth_repository or AuthRepository(job_repository.database_path)
    router = APIRouter(prefix="/v1")
    greeting_generation_ids: set[int] = set()
    greeting_generation_lock = Lock()
    collection_lock = asyncio.Lock()
    scheduled_collection_run_ids: set[int] = set()
    collection_schedule_lock = Lock()

    def current_user(request: Request) -> dict | None:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            claims = verify_token(authorization[7:].strip())
            if claims:
                try:
                    user = auth_repository.get_user(int(claims["sub"]))
                    return user if user.get("isActive") else None
                except (KeyError, ValueError): return None
        # 浏览器扩展通道：配对时由某个登录用户生成配对码，token 直接映射到该用户。
        local_token = request.headers.get("X-Local-Token", "").strip()
        if local_token:
            owner_id = browser_hub.resolve_user(local_token)
            if owner_id is not None:
                try:
                    user = auth_repository.get_user(owner_id)
                    return user if user.get("isActive") else None
                except KeyError: return None
        return None

    def required_user(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="未登录")
        return user

    def runner_authenticated(request: Request) -> bool:
        expected = settings.runner_token
        supplied = request.headers.get("X-Runner-Token", "")
        return bool(expected and supplied and hmac.compare_digest(supplied, expected))

    def require_runner(request: Request) -> None:
        if settings.runner_token and not runner_authenticated(request):
            raise HTTPException(status_code=401, detail="执行器认证失败")

    @router.get("/auth/bootstrap")
    async def auth_bootstrap() -> dict:
        """公开端点：告知前端是否需要创建首个管理员账号（尚未初始化时）。"""
        return {"needsSetup": not auth_repository.has_users()}

    @router.post("/auth/register")
    async def register(request: Request) -> dict:
        # 系统初始化完成后自助注册关闭，账号统一由管理员在“用户管理”中创建。
        if auth_repository.has_users():
            raise HTTPException(status_code=403, detail="注册已关闭，请联系管理员创建账号")
        payload = await request.json()
        try:
            user = auth_repository.create_user(
                str(payload.get("username", "")),
                str(payload.get("password", "")),
                is_admin=True,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"user": user}

    @router.post("/auth/login")
    async def login(request: Request) -> Response:
        payload = await request.json()
        result = auth_repository.authenticate(
            str(payload.get("username", "")), str(payload.get("password", ""))
        )
        if result is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        user, token = result
        jwt = issue_token(user)
        response = Response(content=json.dumps({"user": user, "token": jwt}, ensure_ascii=False), media_type="application/json")
        return response

    @router.post("/auth/logout")
    async def logout(request: Request) -> dict:
        return {"ok": True}

    @router.get("/auth/me")
    async def me(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="未登录")
        return {"user": user}

    @router.get("/admin/users")
    async def admin_users(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="未登录")
        if not user["isAdmin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return {"items": auth_repository.list_users()}

    @router.post("/admin/users")
    async def admin_create_user(request: Request) -> dict:
        admin = required_user(request)
        if not admin["isAdmin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        payload = await request.json()
        try:
            user = auth_repository.create_user(str(payload.get("username", "")), str(payload.get("password", "")), is_admin=bool(payload.get("isAdmin", False)))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"user": user}

    @router.patch("/admin/users/{user_id}")
    async def admin_update_user(user_id: int, request: Request) -> dict:
        admin = required_user(request)
        if not admin["isAdmin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        payload = await request.json()
        if int(admin["id"]) == user_id and (
            payload.get("isActive") is False or payload.get("isAdmin") is False
        ):
            raise HTTPException(status_code=400, detail="不能停用当前管理员或移除自己的管理员权限")
        try:
            target = auth_repository.get_user(user_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="用户不存在") from error
        removes_active_admin = target["isAdmin"] and target["isActive"] and (
            payload.get("isAdmin") is False or payload.get("isActive") is False
        )
        active_admins = [
            item for item in auth_repository.list_users()
            if item["isAdmin"] and item["isActive"]
        ]
        if removes_active_admin and len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="系统至少需要保留一个启用的管理员账号")
        try:
            return {"user": auth_repository.update_user(user_id, password=payload.get("password"), is_admin=payload.get("isAdmin"), is_active=payload.get("isActive"))}
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.delete("/admin/users/{user_id}")
    async def admin_delete_user(user_id: int, request: Request) -> dict:
        admin = required_user(request)
        if not admin["isAdmin"]:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        if int(admin["id"]) == user_id:
            raise HTTPException(status_code=400, detail="不能删除当前管理员账号")
        try:
            target = auth_repository.get_user(user_id)
            if target["isAdmin"] and target["isActive"]:
                active_admins = [
                    item for item in auth_repository.list_users()
                    if item["isAdmin"] and item["isActive"]
                ]
                if len(active_admins) <= 1:
                    raise HTTPException(status_code=409, detail="系统至少需要保留一个启用的管理员账号")
            auth_repository.delete_user(user_id)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=400, detail="用户不存在或无法删除") from error
        return {"ok": True}

    def schedule_automation_collection(
        run_id: int, background_tasks: BackgroundTasks
    ) -> bool:
        """Queue one collection pipeline without allowing duplicate in-process work."""
        with collection_schedule_lock:
            if run_id in scheduled_collection_run_ids:
                return False
            scheduled_collection_run_ids.add(run_id)
        background_tasks.add_task(run_automation_collection_safely, run_id)
        return True

    def collection_is_scheduled(run_id: int) -> bool:
        with collection_schedule_lock:
            return run_id in scheduled_collection_run_ids

    def another_collection_is_scheduled(run_id: int) -> bool:
        with collection_schedule_lock:
            return any(
                queued_run_id != run_id
                for queued_run_id in scheduled_collection_run_ids
            )

    def save_extension_browser_probe(*, boss_logged_in: bool) -> None:
        previous_probe = library_repository.get_setup_state("browser-probe") or {}
        library_repository.save_setup_state(
            "browser-probe",
            {
                "webbridgeRunning": True,
                "kimiExtensionConnected": True,
                "projectExtensionReady": True,
                "bossLoggedIn": boss_logged_in,
                "skillVersion": str(previous_probe.get("skillVersion", "")),
                "source": "extension",
            },
        )

    def string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        return [item.strip() for item in re.split(r"[,，|\n;/；]+", str(value)) if item.strip()]

    def matching_rules(user_id: int = 1) -> list[RiskRuleInput]:
        rules: list[RiskRuleInput] = []
        for record in library_repository.list("rules", user_id=user_id):
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

    def automation_config(user_id: int = 1) -> AutomationConfigResponse:
        profile = library_repository.get_profile(user_id=user_id)
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
            library_repository.get_default_resume_image(user_id=user_id)
            image_available = True
        except KeyError:
            image_available = False
        raw_minimum_salary = profile.get("minimumSalaryK", 20)
        minimum_salary_k = int(
            20 if raw_minimum_salary is None or raw_minimum_salary == "" else raw_minimum_salary
        )
        return AutomationConfigResponse(
            target_roles=target_roles,
            target_cities=target_cities,
            city_code=city_code,
            search_keywords=keywords,
            minimum_salary_k=minimum_salary_k,
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
            matching_rules=matching_rules(user_id),
        )

    def setup_status(user_id: int = 1) -> SetupStatusResponse:
        config = automation_config(user_id)
        models = library_repository.list("models", user_id=user_id)
        all_resumes = library_repository.list("resumes", user_id=user_id)
        resumes = [
            record
            for record in all_resumes
            if record["data"].get("confirmationStatus", "confirmed") == "confirmed"
        ]
        pending_resumes = len(all_resumes) - len(resumes)
        checks = [
            SetupCheck(
                key="local-service",
                label="本地服务",
                status="ready",
                message=f"本地 API v{__version__} 已运行",
            )
        ]

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

        runner = automation_repository.runner_status()
        checks.append(
            SetupCheck(
                key="automation-runner",
                label="自动投递执行器",
                status="ready" if runner["online"] else "blocked",
                message=(
                    f"执行器 {runner['runner_id']} 在线"
                    if runner["online"]
                    else "自动投递执行器未运行，请重新启动 Docker 服务"
                ),
                blocking=not runner["online"],
                action_label="查看安装说明",
                action_path="/setup#services",
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

        browser_state = browser_hub.status()
        browser_connected = bool(browser_state["connected"])
        extension_version = browser_state.get("extensionVersion")
        unified_extension_ready = browser_connected and extension_supports_collection(
            extension_version
        )

        checks.append(
            SetupCheck(
                key="kimi-webbridge",
                label="统一浏览器扩展",
                status="ready" if unified_extension_ready else "blocked",
                message=(
                    f"Chrome 扩展 v{extension_version} 已连接，可搜索、采集并执行投递"
                    if unified_extension_ready
                    else (
                        f"当前扩展 v{extension_version} 不支持当前自动投递协议，"
                        "请重新加载 v0.4.11 或更高版本"
                        if browser_connected
                        else "统一 Chrome 扩展未连接；无需安装 Kimi WebBridge"
                    )
                ),
                blocking=not unified_extension_ready,
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )

        project_extension_ready = unified_extension_ready or bool(
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
                    "统一扩展已连接，可执行简历预览协议"
                    if unified_extension_ready
                    else "项目扩展已在 BOSS 页面显示操作面板"
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
        boss_login_checked = browser_probe is not None
        checks.append(
            SetupCheck(
                key="boss-login",
                label="BOSS 登录",
                status=(
                    "ready"
                    if boss_logged_in
                    else "blocked"
                    if boss_login_checked
                    else "pending"
                ),
                message=(
                    "已确认 BOSS 账号处于登录状态"
                    if boss_logged_in
                    else (
                        "BOSS 登录状态未通过确认"
                        if boss_login_checked
                        else "启动采集时将由统一扩展自动确认 BOSS 登录状态"
                        if unified_extension_ready
                        else "尚未确认 BOSS 登录状态"
                    )
                ),
                blocking=not boss_logged_in and (
                    boss_login_checked or not unified_extension_ready
                ),
                action_label="检查浏览器环境",
                action_path="/setup#browser",
            )
        )

        skill_version = str(browser_probe.get("skillVersion", "")) if browser_probe else ""
        checks.append(
            SetupCheck(
                key="skill-version",
                label="旧版 BOSS Skill（可选）",
                status="ready",
                message=(
                    f"检测到旧版 Skill v{skill_version}；新流程不会调用它"
                    if skill_version
                    else "新流程不需要安装 Skill；职位采集由统一 Chrome 扩展完成"
                ),
                blocking=False,
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

    def build_job_material_context(
        job: StoredJob,
        *,
        user_id: int = 1,
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
        evidence = knowledge_search.search(query, 8, user_id=user_id)
        match = build_automatic_match(match_request, evidence)
        profile = library_repository.get_profile(user_id=user_id)
        resumes = [
            record
            for record in library_repository.list("resumes", user_id=user_id)
            if record["data"].get("confirmationStatus", "confirmed") == "confirmed"
        ]
        default_greeting = str(profile.get("defaultGreeting", "")).strip()
        context = {
            "job": job.model_dump(mode="json", by_alias=True),
            "profile": profile,
            "localEvidence": [
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

    def build_local_job_insight(
        job: StoredJob, match: AutomaticJobMatchResponse
    ) -> dict[str, object]:
        strengths = [
            f"{item.source_name}：{item.content[:120]}"
            for item in match.evidence[:4]
        ]
        gaps = [
            requirement.explanation
            for requirement in match.analysis.risk_requirements
        ]
        if not match.evidence:
            gaps.append("当前知识库没有检索到足够的个人经历证据，匹配结论需要人工核实")
        if match.customization_confidence < 80:
            gaps.append(
                f"定制材料可信度为 {match.customization_confidence}，"
                "建议补充与岗位相关的项目或经历证据"
            )

        strategy_labels = {
            MaterialStrategy.CUSTOM: "可基于现有证据定制问候语和简历",
            MaterialStrategy.DEFAULT: "建议先使用默认材料，并人工确认岗位要求",
            MaterialStrategy.BLOCKED: "当前规则建议暂停投递，先处理风险或补足信息",
        }
        recommendations = [
            strategy_labels[match.decision.material_strategy],
            *match.decision.reasons,
        ]
        recommendations = list(dict.fromkeys(recommendations))
        focus = job.skills[:4] or [job.title]
        interview_questions = [
            f"请准备一个能够证明你具备“{item}”能力的真实案例，说明你的职责、行动和结果。"
            for item in focus
        ]
        conclusion = "建议进一步评估" if match.decision.should_deliver else "当前不建议直接投递"
        return {
            "summary": (
                f"岗位适合度 {match.suitability_score}，材料定制可信度 "
                f"{match.customization_confidence}；{conclusion}。"
            ),
            "strengths": strengths,
            "gaps": list(dict.fromkeys(gaps)),
            "recommendations": recommendations,
            "interviewQuestions": interview_questions,
        }

    def generate_and_store_greeting(snapshot_id: int, user_id: int = 1) -> None:
        try:
            job = job_repository.get(snapshot_id, user_id=user_id)
            if job.generated_greeting:
                return
            context, default_greeting, _ = build_job_material_context(job, user_id=user_id)
            try:
                greeting_context = {
                    key: context[key]
                    for key in (
                        "job",
                        "profile",
                        "localEvidence",
                        "defaultGreeting",
                        "match",
                    )
                }
                generated = greeting_generator.generate(greeting_context, user_id=user_id)
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
            job_repository.update_generated_greeting(snapshot_id, greeting, user_id=user_id)
        except KeyError:
            logger.warning("automatic greeting skipped: job=%s no longer exists", snapshot_id)
        except Exception:
            logger.exception("automatic greeting failed unexpectedly for job=%s", snapshot_id)

    def run_greeting_task(snapshot_id: int, user_id: int = 1) -> None:
        try:
            generate_and_store_greeting(snapshot_id, user_id)
        finally:
            with greeting_generation_lock:
                greeting_generation_ids.discard(snapshot_id)

    def queue_greeting_generation(
        snapshot_id: int, background_tasks: BackgroundTasks, user_id: int = 1
    ) -> None:
        with greeting_generation_lock:
            if snapshot_id in greeting_generation_ids:
                return
            greeting_generation_ids.add(snapshot_id)
        background_tasks.add_task(run_greeting_task, snapshot_id, user_id)

    @router.post("/browser/pairing", response_model=BrowserPairingResponse)
    def create_browser_pairing(http_request: Request) -> BrowserPairingResponse:
        user = required_user(http_request)
        return BrowserPairingResponse.model_validate(
            browser_hub.create_pairing(int(user["id"]))
        )

    @router.get("/browser/status", response_model=BrowserProtocolStatus)
    def get_browser_status(http_request: Request) -> BrowserProtocolStatus:
        required_user(http_request)
        return BrowserProtocolStatus.model_validate(browser_hub.status())

    @router.post("/browser/actions/test", response_model=BrowserActionResponse)
    async def test_browser_action(
        request: BrowserTestActionRequest, http_request: Request
    ) -> BrowserActionResponse:
        required_user(http_request)
        try:
            response = await browser_hub.dispatch(
                run_id=0,
                action=request.action,
                payload=request.payload,
                deadline_ms=5_000,
            )
        except BrowserProtocolError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return BrowserActionResponse.model_validate(response)

    @router.websocket("/browser/ws")
    async def browser_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            hello = await websocket.receive_json()
            if hello.get("type") != "hello" or hello.get("protocolVersion") != PROTOCOL_VERSION:
                await websocket.send_json(
                    {"type": "error", "error": "incompatible browser protocol"}
                )
                await websocket.close(code=1002)
                return
            token = str(hello.get("token", ""))
            if not browser_hub.authenticate(token):
                try:
                    token = browser_hub.exchange_pairing_code(str(hello.get("pairingCode", "")))
                except BrowserProtocolError as error:
                    await websocket.send_json({"type": "error", "error": str(error)})
                    await websocket.close(code=1008)
                    return
                await websocket.send_json(
                    {
                        "type": "paired",
                        "token": token,
                        "protocolVersion": PROTOCOL_VERSION,
                    }
                )
            browser_hub.attach(websocket, str(hello.get("extensionVersion", "unknown")))
            await websocket.send_json(
                {"type": "ready", "protocolVersion": PROTOCOL_VERSION}
            )
            while True:
                response = await websocket.receive_json()
                browser_hub.resolve(response)
        except WebSocketDisconnect:
            pass
        finally:
            browser_hub.detach(websocket)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @router.get("/automation/config", response_model=AutomationConfigResponse)
    def get_automation_config(http_request: Request) -> AutomationConfigResponse:
        user = required_user(http_request)
        return automation_config(int(user["id"]))

    @router.get("/automation/runner/status", response_model=AutomationRunnerStatus)
    def get_automation_runner_status(http_request: Request) -> AutomationRunnerStatus:
        required_user(http_request)
        return AutomationRunnerStatus.model_validate(automation_repository.runner_status())

    @router.post("/automation/runner/heartbeat", response_model=AutomationRunnerStatus)
    def automation_runner_heartbeat(
        request: AutomationHeartbeatRequest, http_request: Request,
    ) -> AutomationRunnerStatus:
        require_runner(http_request)
        return AutomationRunnerStatus.model_validate(
            automation_repository.runner_heartbeat(request.runner_id)
        )

    @router.get("/setup/status", response_model=SetupStatusResponse)
    def get_setup_status(http_request: Request) -> SetupStatusResponse:
        user = required_user(http_request)
        return setup_status(int(user["id"]))

    @router.post("/setup/browser/probe", response_model=BrowserProbeResponse)
    def save_browser_probe(
        request: BrowserProbeRequest, http_request: Request
    ) -> BrowserProbeResponse:
        # 浏览器探针描述的是本机扩展连接状态（设备级），不对单个用户做隔离。
        required_user(http_request)
        state = library_repository.save_setup_state(
            "browser-probe", request.model_dump(mode="json", by_alias=True)
        )
        return BrowserProbeResponse.model_validate(state)

    @router.post("/setup/test-run", response_model=SetupTestRunResponse)
    def run_setup_test(http_request: Request) -> SetupTestRunResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        status_result = setup_status(user_id)
        blocking_checks = [
            check.label
            for check in status_result.checks
            if check.blocking and check.status != "ready"
        ]
        config = automation_config(user_id)
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

    def automation_run(run_id: int, user_id: int | None = None) -> AutomationRun:
        try:
            return AutomationRun.model_validate(
                automation_repository.get_run(run_id, user_id=user_id)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error

    def require_owned_run(run_id: int, http_request: Request) -> tuple[AutomationRun, int]:
        """Resolve the caller's identity and assert they own this automation run."""
        user = required_user(http_request)
        user_id = int(user["id"])
        return automation_run(run_id, user_id), user_id

    def run_owner_id(run_id: int) -> int:
        """Owner of an automation run, used by host-runner driven collection flows."""
        try:
            return int(automation_repository.get_run(run_id).get("user_id") or 1)
        except KeyError:
            return 1

    def validate_planned_job_salaries(
        config_snapshot: dict[str, object],
        planned_jobs: list[dict[str, object]],
        user_id: int = 1,
    ) -> list[dict[str, object]]:
        current_config = automation_config(user_id)
        raw_minimum_salary = config_snapshot.get("minimumSalaryK", 0)
        raw_rules = config_snapshot.get("matchingRules", [])
        try:
            snapshot_minimum_salary_k = int(raw_minimum_salary or 0)
            minimum_salary_k = max(
                snapshot_minimum_salary_k,
                current_config.minimum_salary_k,
            )
            if not isinstance(raw_rules, list):
                raise ValueError("matchingRules must be a list")
            snapshot_rules = [RiskRuleInput.model_validate(rule) for rule in raw_rules]
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail="任务薪资策略配置无效，请重新采集职位并创建任务",
            ) from error
        rules_by_signature: dict[
            tuple[str, str, tuple[str, ...], RuleAction, int, bool], RiskRuleInput
        ] = {}
        for rule in [*snapshot_rules, *current_config.matching_rules]:
            signature = (
                rule.id,
                rule.name,
                tuple(rule.patterns),
                rule.action,
                rule.score_penalty,
                rule.enabled,
            )
            rules_by_signature[signature] = rule
        rules = list(rules_by_signature.values())

        normalized_jobs: list[dict[str, object]] = []
        failures: list[str] = []
        for item in planned_jobs:
            if not isinstance(item, dict):
                failures.append("任务包含无法识别的岗位计划")
                continue
            job = dict(item)
            normalized_salary = normalize_salary_text(
                str(job["salaryText"]) if job.get("salaryText") is not None else None
            )
            job["salaryText"] = normalized_salary
            normalized_jobs.append(job)
            salary_policy = evaluate_salary_policy(
                normalized_salary,
                minimum_salary_k=minimum_salary_k,
                rules=rules,
            )
            if salary_policy.allowed:
                continue
            label = str(
                job.get("companyName")
                or job.get("title")
                or job.get("jobId")
                or "未知岗位"
            )
            reasons = "；".join(
                violation.reason for violation in salary_policy.violations
            )
            failures.append(f"{label}：{reasons}")

        if failures:
            raise HTTPException(
                status_code=422,
                detail="薪资策略校验未通过，已阻止启动：" + "；".join(failures),
            )
        return normalized_jobs

    def approved_browser_payload(
        run: dict[str, object], request: AutomationBrowserActionRequest
    ) -> dict[str, object]:
        """Validate a send capability and replace it with server-owned evidence.

        The approval token is a runner-to-API capability.  It is deliberately
        removed before dispatch so neither the extension nor browser page can
        observe or replay it.
        """
        payload = dict(request.payload)
        if request.action not in {"send_greeting", "send_resume"}:
            return payload
        if run.get("status") != "running":
            raise HTTPException(
                status_code=409,
                detail="发送操作仅允许在已确认且运行中的任务执行",
            )
        config = run.get("config_snapshot")
        if not isinstance(config, dict):
            raise HTTPException(status_code=409, detail="任务缺少已确认的投递清单")
        confirmation = config.get("planConfirmation")
        planned_jobs = config.get("plannedJobs")
        if not isinstance(confirmation, dict) or not isinstance(planned_jobs, list):
            raise HTTPException(status_code=409, detail="任务缺少已确认的投递清单")
        selected_job_ids = confirmation.get("selectedJobIds")
        supplied_token = payload.get("approvalToken")
        if (
            confirmation.get("status") != "confirmed"
            or not isinstance(selected_job_ids, list)
            or request.job_id not in {str(job_id) for job_id in selected_job_ids}
            or not isinstance(supplied_token, str)
            or not automation_repository.approval_token_matches(
                int(run["id"]), supplied_token
            )
        ):
            raise HTTPException(status_code=409, detail="发送操作未获得当前投递清单授权")
        planned_job = next(
            (
                job
                for job in planned_jobs
                if isinstance(job, dict) and str(job.get("jobId", "")) == request.job_id
            ),
            None,
        )
        if planned_job is None:
            raise HTTPException(status_code=409, detail="发送岗位不属于已确认的投递清单")
        expected_fields = {
            "expectedJobId": request.job_id,
            "expectedTitle": str(planned_job.get("title", "")),
            "expectedCompany": str(planned_job.get("companyName", "")),
        }
        if request.action == "send_greeting":
            expected_fields["text"] = str(planned_job.get("greeting", ""))
        if any(payload.get(key) != value or not value for key, value in expected_fields.items()):
            raise HTTPException(
                status_code=409,
                detail="发送内容与用户确认的投递清单不一致",
            )
        payload.pop("approvalToken", None)
        payload.pop("userConfirmed", None)
        payload.pop("planConfirmed", None)
        payload["planConfirmed"] = True
        return payload

    @router.post("/automation/runs", response_model=AutomationRun, status_code=201)
    async def create_automation_run(
        request: AutomationRunCreateRequest,
        background_tasks: BackgroundTasks,
        http_request: Request,
    ) -> AutomationRun:
        user = required_user(http_request)
        user_id = int(user["id"])
        config = automation_config(user_id).model_dump(mode="json", by_alias=True)
        config.update(request.config)
        should_auto_collect = "plannedJobs" not in config
        if "plannedJobs" not in config:
            config["plannedJobs"] = []
            config["collection"] = {
                "status": "pending",
                "phase": "queued",
                "source": "extension",
                "attemptId": 1,
                "collectedCount": 0,
                "analyzedCount": 0,
                "approvedCount": 0,
                "rejectedCount": 0,
                "ruleRejectedCount": 0,
                "duplicateCount": 0,
                "materialErrorCount": 0,
                "analysisErrorCount": 0,
                "reviewedJobs": [],
                "skippedCount": 0,
                "batchNumber": 0,
                "batchLimit": 0,
                "lastBatchCount": 0,
                "partial": False,
                "currentKeyword": None,
                "error": None,
                "queuedAt": datetime.now(UTC).isoformat(),
            }
        elif "collection" not in config:
            planned_jobs = config.get("plannedJobs")
            config["collection"] = {
                "status": "ready",
                "phase": "awaiting_confirmation",
                "source": "provided",
                "attemptId": 0,
                "collectedCount": len(planned_jobs) if isinstance(planned_jobs, list) else 0,
                "analyzedCount": len(planned_jobs) if isinstance(planned_jobs, list) else 0,
                "approvedCount": len(planned_jobs) if isinstance(planned_jobs, list) else 0,
                "rejectedCount": 0,
                "ruleRejectedCount": 0,
                "duplicateCount": 0,
                "materialErrorCount": 0,
                "analysisErrorCount": 0,
                "reviewedJobs": [],
                "currentKeyword": None,
                "error": None,
            }
        created = AutomationRun.model_validate(
            automation_repository.create_run(config, request.target_count, user_id=int(user["id"]))
        )
        if should_auto_collect:
            automation_repository.append_event(
                created.id,
                "collection-queued",
                "info",
                {
                    "attemptId": 1,
                    "phase": "queued",
                    "message": "任务创建后自动进入扩展采集与本地分析流水线",
                },
            )
            schedule_automation_collection(created.id, background_tasks)
        return created

    @router.get("/automation/runs", response_model=AutomationRunListResponse)
    def list_automation_runs(http_request: Request) -> AutomationRunListResponse:
        user = required_user(http_request)
        return AutomationRunListResponse(
            items=[AutomationRun.model_validate(run) for run in automation_repository.list_runs(int(user["id"]))]
        )

    @router.post(
        "/automation/runner/claim", response_model=AutomationRunnerClaimResponse
    )
    def claim_automation_run(
        request: AutomationHeartbeatRequest, http_request: Request,
    ) -> AutomationRunnerClaimResponse:
        require_runner(http_request)
        run = automation_repository.claim_next_run(request.runner_id)
        approval_token = run.pop("approval_token", None) if run else None
        return AutomationRunnerClaimResponse(
            run=AutomationRun.model_validate(run) if run else None,
            approval_token=approval_token,
        )

    @router.post("/automation/runs/{run_id}/heartbeat", response_model=AutomationRun)
    def heartbeat_automation_run(
        run_id: int, request: AutomationHeartbeatRequest, http_request: Request
    ) -> AutomationRun:
        require_runner(http_request)
        try:
            return AutomationRun.model_validate(
                automation_repository.heartbeat(run_id, request.runner_id)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/automation/runs/{run_id}/progress", response_model=AutomationRun)
    def update_automation_progress(
        run_id: int, request: AutomationProgressRequest, http_request: Request
    ) -> AutomationRun:
        require_runner(http_request)
        try:
            automation_repository.heartbeat(run_id, request.runner_id)
            return AutomationRun.model_validate(
                automation_repository.record_progress(
                    run_id, request.job_id, request.outcome, request.reason
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/automation/runs/{run_id}/runner-finish", response_model=AutomationRun)
    def finish_automation_run(
        run_id: int, request: AutomationRunnerFinishRequest, http_request: Request
    ) -> AutomationRun:
        require_runner(http_request)
        try:
            automation_repository.heartbeat(run_id, request.runner_id)
            return AutomationRun.model_validate(
                automation_repository.transition(run_id, request.status, request.reason)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post(
        "/automation/runs/{run_id}/browser-action",
        response_model=AutomationBrowserActionResponse,
    )
    async def execute_automation_browser_action(
        run_id: int, request: AutomationBrowserActionRequest, http_request: Request
    ) -> AutomationBrowserActionResponse:
        require_runner(http_request)
        if request.action not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=422, detail="unsupported browser action")
        if request.action in {"send_greeting", "send_resume"} and not all(
            request.payload.get(field) for field in ("expectedTitle", "expectedCompany")
        ):
            raise HTTPException(
                status_code=422,
                detail="send actions require expectedTitle and expectedCompany",
            )
        try:
            claimed_run = automation_repository.heartbeat(run_id, request.runner_id)
            dispatch_payload = approved_browser_payload(claimed_run, request)
            action, execute = automation_repository.claim_action(
                run_id, request.job_id, request.action
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not execute:
            replay_status = (
                "success"
                if action["status"] == "succeeded"
                else "uncertain"
                if action["status"] == "uncertain"
                else "blocked"
            )
            return AutomationBrowserActionResponse(
                idempotency_key=action["idempotency_key"],
                execute=False,
                result=BrowserActionResponse(
                    request_id=action["idempotency_key"],
                    status=replay_status,
                    evidence={"idempotentReplay": True},
                    error=(
                        "existing action is not safe to execute again"
                        if replay_status != "success"
                        else None
                    ),
                ),
            )
        try:
            result = await browser_hub.dispatch(
                run_id=run_id,
                action=request.action,
                payload=dispatch_payload,
                deadline_ms=request.deadline_ms,
            )
            parsed = BrowserActionResponse.model_validate(result)
            succeeded = None if parsed.status == "uncertain" else parsed.status == "success"
            automation_repository.finish_action(
                action["idempotency_key"],
                succeeded=succeeded,
                error=parsed.error,
                evidence=parsed.evidence,
            )
            return AutomationBrowserActionResponse(
                idempotency_key=action["idempotency_key"],
                execute=True,
                result=parsed,
            )
        except BrowserProtocolError as error:
            automation_repository.finish_action(
                action["idempotency_key"], succeeded=False, error=str(error)
            )
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post(
        "/automation/runs/{run_id}/actions/claim",
        response_model=AutomationActionClaimResponse,
    )
    def claim_automation_action(
        run_id: int, request: AutomationActionClaimRequest, http_request: Request
    ) -> AutomationActionClaimResponse:
        require_runner(http_request)
        try:
            action, execute = automation_repository.claim_action(
                run_id, request.job_id, request.action_type
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        return AutomationActionClaimResponse(action=action, execute=execute)

    @router.post(
        "/automation/actions/{idempotency_key:path}/result",
        response_model=AutomationActionClaimResponse,
    )
    def finish_automation_action(
        idempotency_key: str, request: AutomationActionResultRequest, http_request: Request
    ) -> AutomationActionClaimResponse:
        require_runner(http_request)
        try:
            action = automation_repository.finish_action(
                idempotency_key,
                succeeded=request.succeeded,
                error=request.error,
                evidence=request.evidence,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation action not found") from error
        return AutomationActionClaimResponse(action=action, execute=False)

    @router.get("/automation/runs/{run_id}", response_model=AutomationRun)
    def get_automation_run(run_id: int, http_request: Request) -> AutomationRun:
        if runner_authenticated(http_request):
            return automation_run(run_id)
        user = required_user(http_request)
        return automation_run(run_id, int(user["id"]))

    @router.get("/automation/runs/{run_id}/report", response_model=AutomationReport)
    def get_automation_report(run_id: int, http_request: Request) -> AutomationReport:
        user = required_user(http_request)
        try:
            return AutomationReport.model_validate(
                automation_repository.report(run_id, user_id=int(user["id"]))
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error

    @router.post("/automation/runs/{run_id}/start", response_model=AutomationRun)
    def start_automation_run(
        run_id: int,
        http_request: Request,
        request: AutomationRunStartRequest | None = None,
    ) -> AutomationRun:
        user = required_user(http_request)
        user_id = int(user["id"])
        run = automation_run(run_id, user_id)
        if collection_lock.locked() or another_collection_is_scheduled(run_id):
            raise HTTPException(
                status_code=409,
                detail="职位采集或本地分析仍在进行，请等待企业确认清单生成",
            )
        if run.status == "interrupted":
            planned_jobs = run.config_snapshot.get("plannedJobs", [])
            if not isinstance(planned_jobs, list) or not planned_jobs:
                return AutomationRun.model_validate(
                    automation_repository.transition(
                        run_id,
                        "blocked",
                        "没有可执行的岗位计划；请先采集岗位，再新建任务",
                    )
                )
            validate_planned_job_salaries(run.config_snapshot, planned_jobs, user_id)
            status_result = setup_status(user_id)
            blockers = [
                check.label
                for check in status_result.checks
                if check.blocking and check.status != "ready"
            ]
            if blockers:
                return AutomationRun.model_validate(
                    automation_repository.transition(run_id, "blocked", "、".join(blockers))
                )
            return AutomationRun.model_validate(automation_repository.transition(run_id, "running"))
        if run.status != "draft":
            raise HTTPException(status_code=409, detail=f"run cannot start from {run.status}")
        active = [
            item
            for item in automation_repository.list_runs(user_id)
            if item["id"] != run_id and item["status"] in {"running", "paused", "stopping"}
        ]
        if active:
            raise HTTPException(status_code=409, detail="another automation run is active")
        collection = run.config_snapshot.get("collection", {})
        if isinstance(collection, dict) and collection.get("status") != "ready":
            raise HTTPException(status_code=409, detail="请先通过 Chrome 扩展完成职位采集")
        if request is None or not request.selected_job_ids:
            raise HTTPException(status_code=422, detail="请先确认至少一个待投企业")
        requested_ids = request.selected_job_ids
        if len(requested_ids) != len(set(requested_ids)):
            raise HTTPException(status_code=422, detail="待投岗位不能重复选择")
        planned_jobs = run.config_snapshot.get("plannedJobs", [])
        if not isinstance(planned_jobs, list):
            planned_jobs = []
        jobs_by_id = {
            str(job.get("jobId")): job
            for job in planned_jobs
            if isinstance(job, dict) and job.get("jobId")
        }
        missing_ids = [job_id for job_id in requested_ids if job_id not in jobs_by_id]
        if missing_ids:
            raise HTTPException(status_code=422, detail="所选岗位不属于当前任务计划")
        selected_jobs = validate_planned_job_salaries(
            run.config_snapshot,
            [jobs_by_id[job_id] for job_id in requested_ids],
            user_id,
        )
        run = AutomationRun.model_validate(
            automation_repository.confirm_plan(
                run_id, selected_jobs
            )
        )
        automation_repository.transition(run_id, "validating")
        planned_jobs = run.config_snapshot.get("plannedJobs", [])
        if not isinstance(planned_jobs, list) or not planned_jobs:
            return AutomationRun.model_validate(
                automation_repository.transition(
                    run_id,
                    "blocked",
                    "没有可执行的岗位计划；请先采集岗位，再新建任务",
                )
            )
        status_result = setup_status(user_id)
        blockers = [
            check.label
            for check in status_result.checks
            if check.blocking and check.status != "ready"
        ]
        if blockers:
            return AutomationRun.model_validate(
                automation_repository.transition(run_id, "blocked", "、".join(blockers))
            )
        automation_repository.transition(run_id, "ready")
        running = automation_repository.transition(run_id, "running")
        automation_repository.append_event(
            run_id,
            "runner-awaiting-host",
            "info",
            {"message": "任务已创建，等待宿主机执行器认领"},
        )
        return AutomationRun.model_validate(running)

    @router.post("/automation/runs/{run_id}/pause", response_model=AutomationRun)
    def pause_automation_run(run_id: int, http_request: Request) -> AutomationRun:
        require_owned_run(run_id, http_request)
        try:
            return AutomationRun.model_validate(automation_repository.transition(run_id, "paused"))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/automation/runs/{run_id}/resume", response_model=AutomationRun)
    def resume_automation_run(run_id: int, http_request: Request) -> AutomationRun:
        run, user_id = require_owned_run(run_id, http_request)
        planned_jobs = run.config_snapshot.get("plannedJobs", [])
        if not isinstance(planned_jobs, list) or not planned_jobs:
            raise HTTPException(status_code=422, detail="没有可执行的岗位计划")
        validate_planned_job_salaries(run.config_snapshot, planned_jobs, user_id)
        try:
            return AutomationRun.model_validate(automation_repository.transition(run_id, "running"))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/automation/runs/{run_id}/retry", response_model=AutomationRun)
    def retry_automation_run(run_id: int, http_request: Request) -> AutomationRun:
        source, user_id = require_owned_run(run_id, http_request)
        if source.status not in {"blocked", "failed", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"run cannot retry from {source.status}",
            )
        active = [
            item
            for item in automation_repository.list_runs(user_id)
            if item["id"] != run_id and item["status"] in {"running", "paused", "stopping"}
        ]
        if active:
            raise HTTPException(status_code=409, detail="another automation run is active")

        planned_jobs = source.config_snapshot.get("plannedJobs", [])
        if not isinstance(planned_jobs, list):
            planned_jobs = []
        report = automation_repository.report(run_id, user_id=user_id)
        succeeded_job_ids = {
            str(event["payload"].get("jobId", ""))
            for event in report["events"]
            if event["event_type"] == "job-finished"
            and event["payload"].get("outcome") == "success"
        }
        succeeded_actions = {
            (str(action["job_id"]), str(action["action_type"]))
            for action in report["actions"]
            if action["status"] == "succeeded"
        }
        retry_jobs: list[dict[str, Any]] = []
        for raw_job in planned_jobs:
            if not isinstance(raw_job, dict):
                continue
            job_id = str(raw_job.get("jobId", ""))
            if not job_id or job_id in succeeded_job_ids:
                continue
            job = dict(raw_job)
            if (job_id, "send_greeting") in succeeded_actions:
                job["retrySkipGreeting"] = True
            if (job_id, "send_resume") in succeeded_actions:
                job["retrySkipResume"] = True
            retry_jobs.append(job)
        if not retry_jobs:
            raise HTTPException(status_code=409, detail="没有失败或未完成的岗位可以重试")

        validate_planned_job_salaries(source.config_snapshot, retry_jobs, user_id)
        retry_config = dict(source.config_snapshot)
        retry_config["plannedJobs"] = retry_jobs
        retry_config["retryOfRunId"] = run_id
        retry_config["retryReason"] = source.stop_reason
        created = automation_repository.create_run(retry_config, len(retry_jobs), user_id=user_id)
        retry_run_id = int(created["id"])
        automation_repository.append_event(
            retry_run_id,
            "retry-created",
            "warning",
            {
                "sourceRunId": run_id,
                "jobCount": len(retry_jobs),
                "message": f"用户确认重试任务 #{run_id} 的失败或未完成岗位",
            },
        )
        automation_repository.confirm_plan(retry_run_id, retry_jobs)
        automation_repository.transition(retry_run_id, "validating")
        status_result = setup_status(user_id)
        blockers = [
            check.label
            for check in status_result.checks
            if check.blocking and check.status != "ready"
        ]
        if blockers:
            return AutomationRun.model_validate(
                automation_repository.transition(retry_run_id, "blocked", "、".join(blockers))
            )
        automation_repository.transition(retry_run_id, "ready")
        running = automation_repository.transition(retry_run_id, "running")
        automation_repository.append_event(
            retry_run_id,
            "runner-awaiting-host",
            "info",
            {"message": "重试任务已创建，等待宿主机执行器认领"},
        )
        return AutomationRun.model_validate(running)

    @router.post("/automation/runs/{run_id}/stop", response_model=AutomationRun)
    def stop_automation_run(run_id: int, http_request: Request) -> AutomationRun:
        require_owned_run(run_id, http_request)
        try:
            automation_repository.transition(run_id, "stopping", "user-requested")
            return AutomationRun.model_validate(
                automation_repository.transition(run_id, "cancelled", "user-requested")
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get(
        "/automation/runs/{run_id}/events", response_model=AutomationEventListResponse
    )
    def list_automation_events(run_id: int, http_request: Request) -> AutomationEventListResponse:
        require_owned_run(run_id, http_request)
        try:
            events = automation_repository.list_events(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="automation run not found") from error
        return AutomationEventListResponse(items=events)

    @router.get("/automation/runs/{run_id}/events/stream")
    def stream_automation_events(
        run_id: int, http_request: Request, after: int = 0
    ) -> StreamingResponse:
        require_owned_run(run_id, http_request)

        def events():
            cursor = after
            idle = 0
            while idle < 30:
                current = automation_repository.list_events(run_id)
                unseen = [event for event in current if event["sequence"] > cursor]
                if unseen:
                    idle = 0
                    for event in unseen:
                        cursor = event["sequence"]
                        payload = json.dumps(event, ensure_ascii=False, default=str)
                        yield f"id: {cursor}\ndata: {payload}\n\n"
                else:
                    idle += 1
                    yield ": heartbeat\n\n"
                time.sleep(1)

        return StreamingResponse(events(), media_type="text/event-stream")

    @router.post("/client-logs", response_model=ClientLogRecord, status_code=201)
    def create_client_log(request: ClientLogInput, http_request: Request) -> ClientLogRecord:
        user = required_user(http_request)
        record = ClientLogRecord.model_validate(
            client_log_repository.create(
                request.model_dump(by_alias=False), user_id=int(user["id"])
            )
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
    def list_client_logs(
        http_request: Request, limit: int = Query(default=100, ge=1, le=500)
    ) -> ClientLogListResponse:
        user = required_user(http_request)
        return ClientLogListResponse(
            items=client_log_repository.list_recent(limit, user_id=int(user["id"]))
        )

    @router.post("/deliveries", response_model=DeliveryRecord, status_code=201)
    def save_delivery(request: DeliveryRecordInput, http_request: Request) -> DeliveryRecord:
        # 扩展通过 X-Local-Token 访问，身份解析在 current_user 内统一处理。
        user = required_user(http_request)
        return delivery_repository.upsert(request, user_id=int(user["id"]))

    @router.get("/deliveries", response_model=DeliveryListResponse)
    def list_deliveries(
        http_request: Request, limit: int = Query(default=100, ge=1, le=500)
    ) -> DeliveryListResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        return DeliveryListResponse(
            total=delivery_repository.count(user_id=user_id),
            items=delivery_repository.list_recent(limit, user_id=user_id),
        )

    @router.post("/decisions/evaluate", response_model=DecisionResponse)
    def evaluate_decision(request: DecisionRequest) -> DecisionResponse:
        return evaluate_material_strategy(request)

    @router.post("/jobs/capture", response_model=JobCaptureResponse)
    def capture_jobs(
        request: JobCaptureRequest, background_tasks: BackgroundTasks, http_request: Request
    ) -> JobCaptureResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        job_ids = job_repository.save_many(request.jobs, user_id=user_id)
        for captured in request.jobs:
            try:
                stored = job_repository.get_by_platform_job_id(
                    captured.platform, captured.platform_job_id, user_id=user_id
                )
            except KeyError:
                continue
            if not stored.generated_greeting:
                queue_greeting_generation(stored.id, background_tasks, user_id)
        return JobCaptureResponse(accepted=len(job_ids), job_ids=job_ids)

    @router.get("/jobs", response_model=JobListResponse)
    def list_jobs(
        background_tasks: BackgroundTasks,
        http_request: Request,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
        query: str | None = Query(default=None, max_length=300),
        communication_result: Literal[
            "not_communicated", "communicated", "interviewed"
        ] | None = Query(default=None, alias="communicationResult"),
    ) -> JobListResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        total = job_repository.count(query, communication_result, user_id=user_id)
        total_pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        items = job_repository.list_recent(
            page_size,
            offset=(current_page - 1) * page_size,
            query=query,
            communication_result=communication_result,
            user_id=user_id,
        )
        # Automation collection writes snapshots through analyze-and-plan instead
        # of /jobs/capture. Older runs therefore left rejected snapshots without a
        # preview greeting. Lazily repair visible rows without delaying the list
        # response; delivery eligibility remains a separate decision.
        for item in items:
            if not item.generated_greeting:
                queue_greeting_generation(item.id, background_tasks, user_id)
        return JobListResponse(
            total=total,
            page=current_page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    @router.post("/jobs", response_model=StoredJob, status_code=201)
    def create_job(
        request: ManualJobInput, background_tasks: BackgroundTasks, http_request: Request
    ) -> StoredJob:
        user = required_user(http_request)
        user_id = int(user["id"])
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
        stored = job_repository.create(job, user_id=user_id)
        if not stored.generated_greeting:
            queue_greeting_generation(stored.id, background_tasks, user_id)
        return stored

    @router.put("/jobs/{snapshot_id}/tracking", response_model=StoredJob)
    def update_job_tracking(
        snapshot_id: int, request: JobTrackingUpdate, http_request: Request
    ) -> StoredJob:
        user = required_user(http_request)
        try:
            return job_repository.update_tracking(
                snapshot_id, request.model_dump(by_alias=False), user_id=int(user["id"])
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job snapshot not found") from error

    @router.delete("/jobs/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_job(snapshot_id: int, http_request: Request) -> Response:
        user = required_user(http_request)
        if not job_repository.delete(snapshot_id, user_id=int(user["id"])):
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
    def match_job(
        request: AutomaticJobMatchRequest, http_request: Request
    ) -> AutomaticJobMatchResponse:
        user = required_user(http_request)
        query = "\n".join(
            part for part in [request.title, " ".join(request.skills), request.job_text] if part
        )
        evidence = knowledge_search.search(query, 8, user_id=int(user["id"]))
        return build_automatic_match(request, evidence)

    def resolve_job_plan(
        job: CapturedJob,
        *,
        user_id: int,
        minimum_suitability_score: int | None = None,
        minimum_customization_confidence: int | None = None,
        company_blocked: bool = False,
    ) -> JobAnalysisPlanResponse:
        """岗位分析入口：采集流水线与 HTTP 端点共用，因此不依赖 Request 对象。"""
        job_repository.save_many([job], user_id=user_id)
        job = job_repository.get_by_platform_job_id(
            job.platform, job.platform_job_id, user_id=user_id
        )
        config = automation_config(user_id)
        suitability_threshold = (
            minimum_suitability_score
            if minimum_suitability_score is not None
            else config.minimum_suitability_score
        )
        confidence_threshold = (
            minimum_customization_confidence
            if minimum_customization_confidence is not None
            else config.minimum_customization_confidence
        )
        context, default_greeting, match = build_job_material_context(
            job,
            user_id=user_id,
            minimum_suitability_score=suitability_threshold,
            minimum_customization_confidence=confidence_threshold,
            rules=config.matching_rules,
            duplicate=job.has_communicated,
            company_blocked=company_blocked,
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

        salary_policy = evaluate_salary_policy(
            job.salary_text,
            minimum_salary_k=config.minimum_salary_k,
            rules=config.matching_rules,
        )
        if not salary_policy.allowed:
            existing_rule_ids = {
                rule_match.rule_id for rule_match in match.decision.rule_matches
            }
            salary_rule_matches = [
                RuleMatch(
                    rule_id=violation.rule_id,
                    rule_name=violation.rule_name,
                    action=RuleAction.BLOCK_DELIVERY,
                    evidence=list(violation.evidence),
                )
                for violation in salary_policy.violations
                if violation.rule_id not in existing_rule_ids
            ]
            salary_reasons = [
                violation.reason for violation in salary_policy.violations
            ]
            match = match.model_copy(
                update={
                    "decision": match.decision.model_copy(
                        update={
                            "material_strategy": MaterialStrategy.BLOCKED,
                            "should_deliver": False,
                            "reasons": list(
                                dict.fromkeys(
                                    [
                                        *(
                                            []
                                            if match.decision.should_deliver
                                            else match.decision.reasons
                                        ),
                                        *salary_reasons,
                                    ]
                                )
                            ),
                            "rule_matches": [
                                *match.decision.rule_matches,
                                *salary_rule_matches,
                            ],
                        }
                    )
                }
            )

        greeting: str | None = job.generated_greeting
        if not greeting:
            try:
                greeting_context = {
                    key: context[key]
                    for key in (
                        "job",
                        "profile",
                        "localEvidence",
                        "defaultGreeting",
                        "match",
                    )
                }
                greeting_context["match"] = {
                    "suitabilityScore": match.suitability_score,
                    "customizationConfidence": match.customization_confidence,
                    "materialStrategy": match.decision.material_strategy,
                    "shouldDeliver": match.decision.should_deliver,
                    "reasons": match.decision.reasons,
                }
                generated = greeting_generator.generate(greeting_context, user_id=user_id)
                greeting = str(generated["greeting"]).strip()
            except (RuntimeError, KeyError, TypeError) as error:
                logger.warning("planned greeting fell back for job=%s: %s", job.id, error)
            greeting = greeting or default_greeting or (
                f"您好，我对贵司的{job.title}岗位很感兴趣，希望有机会进一步沟通，谢谢。"
            )
            job = job_repository.update_generated_greeting(job.id, greeting, user_id=user_id)

        return JobAnalysisPlanResponse(
            snapshot=job,
            match=match,
            generated_greeting=greeting,
            default_resume_image_available=config.default_resume_image_available,
            duplicate=job.has_communicated,
        )

    @router.post("/jobs/analyze-and-plan", response_model=JobAnalysisPlanResponse)
    def analyze_and_plan_job(
        request: JobAnalysisPlanRequest, http_request: Request
    ) -> JobAnalysisPlanResponse:
        user = required_user(http_request)
        return resolve_job_plan(
            request.job,
            user_id=int(user["id"]),
            minimum_suitability_score=request.minimum_suitability_score,
            minimum_customization_confidence=request.minimum_customization_confidence,
            company_blocked=request.company_blocked,
        )

    @router.post(
        "/automation/runs/{run_id}/collect",
        response_model=AutomationRun,
        status_code=202,
    )
    async def queue_automation_collection(
        run_id: int, background_tasks: BackgroundTasks, http_request: Request
    ) -> AutomationRun:
        """Queue or recover collection and return immediately.

        This endpoint is intentionally idempotent. A ``collecting`` state without an
        in-memory task is treated as an interrupted service process and is queued
        again from persisted configuration.
        """
        run, _user_id = require_owned_run(run_id, http_request)
        if run.status != "draft":
            raise HTTPException(status_code=409, detail=f"run cannot collect from {run.status}")
        collection = run.config_snapshot.get("collection", {})
        collection_state = (
            str(collection.get("status", "pending"))
            if isinstance(collection, dict)
            else "pending"
        )
        if collection_state == "ready":
            return run
        if collection_is_scheduled(run_id):
            return run
        previous_attempt_id = (
            int(collection.get("attemptId", 0) or 0)
            if isinstance(collection, dict)
            else 0
        )
        attempt_id = previous_attempt_id + 1

        queued = AutomationRun.model_validate(
            automation_repository.update_collection(
                run_id,
                "pending",
                planned_jobs=[],
                details={
                    "phase": "queued",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "collectedCount": 0,
                    "analyzedCount": 0,
                    "approvedCount": 0,
                    "rejectedCount": 0,
                    "ruleRejectedCount": 0,
                    "duplicateCount": 0,
                    "materialErrorCount": 0,
                    "analysisErrorCount": 0,
                    "reviewedJobs": [],
                    "skippedCount": 0,
                    "batchNumber": 0,
                    "batchLimit": 0,
                    "lastBatchCount": 0,
                    "partial": False,
                    "error": None,
                    "queuedAt": datetime.now(UTC).isoformat(),
                    "startedAt": None,
                    "completedAt": None,
                    "failedAt": None,
                    "browserErrors": [],
                    "analysisErrors": [],
                },
            )
        )
        schedule_automation_collection(run_id, background_tasks)
        return queued

    async def run_automation_collection_safely(run_id: int) -> None:
        """Execute an automatically queued pipeline and persist every failure."""
        try:
            await collect_and_analyze_automation_jobs(run_id)
        except HTTPException as error:
            logger.warning(
                "automation collection failed run=%s status=%s: %s",
                run_id,
                error.status_code,
                error.detail,
            )
        except Exception as error:  # noqa: BLE001 - background jobs must persist failures
            logger.exception("automation collection crashed run=%s", run_id)
            try:
                run = automation_run(run_id)
                if run.status == "draft":
                    collection = run.config_snapshot.get("collection", {})
                    attempt_id = (
                        int(collection.get("attemptId", 0) or 0)
                        if isinstance(collection, dict)
                        else 0
                    )
                    automation_repository.update_collection(
                        run_id,
                        "failed",
                        planned_jobs=[],
                        details={
                            "phase": "failed",
                            "source": "extension",
                            "attemptId": attempt_id,
                            "currentKeyword": None,
                            "error": f"自动采集异常：{error}",
                            "failedAt": datetime.now(UTC).isoformat(),
                        },
                    )
            except (HTTPException, KeyError, ValueError):
                logger.exception("failed to persist collection crash run=%s", run_id)
        finally:
            with collection_schedule_lock:
                scheduled_collection_run_ids.discard(run_id)

    async def collect_and_analyze_automation_jobs(run_id: int, user_id: int | None = None) -> AutomationRun:
        """Collect through the extension, then analyze locally without any send action."""
        run = automation_run(run_id)
        if user_id is None:
            user_id = run_owner_id(run_id)
        if run.status != "draft":
            raise HTTPException(status_code=409, detail=f"run cannot collect from {run.status}")
        config = run.config_snapshot
        collection_state = config.get("collection", {})
        attempt_id = (
            int(collection_state.get("attemptId", 0) or 0)
            if isinstance(collection_state, dict)
            else 0
        )
        active = [
            item
            for item in automation_repository.list_runs()
            if item["id"] != run_id and item["status"] in {"running", "paused", "stopping"}
        ]
        if active:
            reason = "有投递任务正在使用浏览器，请暂停或结束后再采集"
            automation_repository.update_collection(
                run_id,
                "failed",
                planned_jobs=[],
                details={
                    "phase": "failed",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "error": reason,
                    "failedAt": datetime.now(UTC).isoformat(),
                },
            )
            raise HTTPException(
                status_code=409,
                detail=reason,
            )

        raw_keywords = config.get("searchKeywords", [])
        keywords = [
            str(keyword).strip()
            for keyword in raw_keywords
            if str(keyword).strip()
        ] if isinstance(raw_keywords, list) else []
        if not keywords:
            reason = "请先在个人资料中配置搜索关键词"
            automation_repository.update_collection(
                run_id,
                "failed",
                planned_jobs=[],
                details={
                    "phase": "failed",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "error": reason,
                    "failedAt": datetime.now(UTC).isoformat(),
                },
            )
            raise HTTPException(status_code=422, detail=reason)
        browser_state = browser_hub.status()
        if not browser_state["connected"]:
            automation_repository.update_collection(
                run_id,
                "failed",
                planned_jobs=[],
                details={
                    "phase": "failed",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "error": "统一 Chrome 扩展未连接",
                    "failedAt": datetime.now(UTC).isoformat(),
                },
            )
            raise HTTPException(status_code=409, detail="统一 Chrome 扩展未连接")
        if not extension_supports_collection(browser_state.get("extensionVersion")):
            version = browser_state.get("extensionVersion") or "未知"
            reason = (
                f"当前扩展 v{version} 不支持当前自动投递协议，"
                        "请重新加载 v0.4.11 或更高版本"
            )
            automation_repository.update_collection(
                run_id,
                "failed",
                planned_jobs=[],
                details={
                    "phase": "failed",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "error": reason,
                    "failedAt": datetime.now(UTC).isoformat(),
                },
            )
            raise HTTPException(status_code=409, detail=reason)

        target_count = run.target_count
        # Rule rejection rates vary widely by keyword. A small target-derived
        # multiplier (for example 3 targets -> 9 candidates) can stop while the
        # same BOSS result page still contains many viable cards. Keep scanning
        # across lazy-loaded results and configured keywords, with a hard safety
        # cap to avoid an unbounded browser run.
        try:
            configured_candidate_limit = int(config.get("candidateLimit", 100) or 100)
        except (TypeError, ValueError):
            configured_candidate_limit = 100
        candidate_limit = max(target_count, min(configured_candidate_limit, 500))
        try:
            configured_interval_ms = int(config.get("collectionIntervalMs", 2_000) or 0)
        except (TypeError, ValueError):
            configured_interval_ms = 2_000
        collection_interval_ms = max(0, min(configured_interval_ms, 30_000))
        raw_collection_filters = config.get("collectionFilters")
        collection_filters = {
            key: str(raw_collection_filters.get(key, "")).strip()
            for key in COLLECTION_FILTER_KEYS
            if isinstance(raw_collection_filters, dict)
            and re.fullmatch(
                r"\d+(?:,\d+)*",
                str(raw_collection_filters.get(key, "")).strip(),
            )
        }
        historical_job_ids = set(
            await run_in_threadpool(
                job_repository.list_platform_job_ids, "boss", user_id=user_id
            )
        )
        captured: dict[str, CapturedJob] = {}
        browser_errors: list[str] = []
        skipped_count = 0
        exhausted_without_new_jobs = False

        async with collection_lock:
            try:
                session = BrowserActionResponse.model_validate(
                    await browser_hub.dispatch(
                        run_id=run_id,
                        action="session_status",
                        payload={},
                        deadline_ms=30_000,
                    )
                )
            except BrowserProtocolError as error:
                reason = browser_protocol_error_message(error, "session_status")
                automation_repository.update_collection(
                    run_id,
                    "failed",
                    planned_jobs=[],
                    details={
                        "phase": "failed",
                        "source": "extension",
                        "attemptId": attempt_id,
                        "currentKeyword": None,
                        "collectedCount": 0,
                        "approvedCount": 0,
                        "error": reason,
                        "failedAt": datetime.now(UTC).isoformat(),
                    },
                )
                raise HTTPException(status_code=409, detail=reason) from error

            logged_in = session.evidence.get("loggedIn")
            if session.status != "success" or logged_in is not True:
                if logged_in is False:
                    save_extension_browser_probe(boss_logged_in=False)
                reason = (
                    session.error or "BOSS 登录状态无效，请先在 BOSS 页面完成登录"
                    if logged_in is False
                    else session.error or "扩展未能确认 BOSS 登录状态，请重新加载扩展"
                )
                automation_repository.update_collection(
                    run_id,
                    "failed",
                    planned_jobs=[],
                    details={
                        "phase": "failed",
                        "source": "extension",
                        "attemptId": attempt_id,
                        "currentKeyword": None,
                        "collectedCount": 0,
                        "approvedCount": 0,
                        "error": reason,
                        "failedAt": datetime.now(UTC).isoformat(),
                    },
                )
                raise HTTPException(status_code=409, detail=reason)

            save_extension_browser_probe(boss_logged_in=True)
            automation_repository.update_collection(
                run_id,
                "collecting",
                planned_jobs=[],
                details={
                    "phase": "searching",
                    "source": "extension",
                    "attemptId": attempt_id,
                    "requestedTarget": target_count,
                    "candidateLimit": candidate_limit,
                    "collectionIntervalMs": collection_interval_ms,
                    "collectionFilters": collection_filters,
                    "existingExcludedCount": len(historical_job_ids),
                    "collectedCount": 0,
                    "analyzedCount": 0,
                    "approvedCount": 0,
                    "rejectedCount": 0,
                    "ruleRejectedCount": 0,
                    "duplicateCount": 0,
                    "materialErrorCount": 0,
                    "analysisErrorCount": 0,
                    "reviewedJobs": [],
                    "currentKeyword": None,
                    "keywords": keywords,
                    "startedAt": datetime.now(UTC).isoformat(),
                    "completedAt": None,
                    "failedAt": None,
                    "browserErrors": [],
                    "analysisErrors": [],
                    "error": None,
                },
            )
            automation_repository.append_event(
                run_id,
                "collection-stage-changed",
                "info",
                {
                    "phase": "searching",
                    "message": "扩展将按搜索关键词采集职位",
                },
            )
            halt_collection = False
            for keyword in keywords:
                if len(captured) >= candidate_limit or halt_collection:
                    break
                automation_repository.update_collection(
                    run_id,
                    "collecting",
                    details={
                        "phase": "searching",
                        "currentKeyword": keyword,
                        "collectedCount": len(captured),
                    },
                    emit_event=False,
                )
                automation_repository.append_event(
                    run_id,
                    "collection-keyword",
                    "info",
                    {"keyword": keyword, "phase": "searching"},
                )
                try:
                    navigation = BrowserActionResponse.model_validate(
                        await browser_hub.dispatch(
                            run_id=run_id,
                            action="navigate_search",
                            payload={
                                "query": keyword,
                                "cityCode": config.get("cityCode", ""),
                                "filters": collection_filters,
                            },
                            deadline_ms=30_000,
                        )
                    )
                except BrowserProtocolError as error:
                    reason = browser_protocol_error_message(error, "navigate_search")
                    browser_errors.append(f"{keyword}：{reason}")
                    automation_repository.append_event(
                        run_id,
                        "collection-keyword",
                        "warning",
                        {"keyword": keyword, "phase": "failed", "error": reason},
                    )
                    continue
                if navigation.status != "success":
                    browser_errors.append(
                        f"{keyword}：{navigation.error or '打开搜索页失败'}"
                    )
                    automation_repository.append_event(
                        run_id,
                        "collection-keyword",
                        "warning",
                        {
                            "currentKeyword": keyword,
                            "phase": "failed",
                            "error": navigation.error,
                        },
                    )
                    continue

                batch_number = 0
                while len(captured) < candidate_limit:
                    batch_number += 1
                    remaining = candidate_limit - len(captured)
                    batch_limit = min(COLLECTION_BATCH_SIZE, remaining)
                    batch_deadline_ms = min(
                        MAX_COLLECTION_BATCH_DEADLINE_MS,
                        COLLECTION_BATCH_DEADLINE_MS
                        + collection_interval_ms * batch_limit,
                    )
                    excluded_job_ids = sorted(historical_job_ids | set(captured))
                    automation_repository.update_collection(
                        run_id,
                        "collecting",
                        details={
                            "phase": "collecting",
                            "currentKeyword": keyword,
                            "collectedCount": len(captured),
                            "batchNumber": batch_number,
                            "batchLimit": batch_limit,
                            "batchDeadlineMs": batch_deadline_ms,
                        },
                        emit_event=False,
                    )
                    if batch_number == 1:
                        automation_repository.append_event(
                            run_id,
                            "collection-stage-changed",
                            "info",
                            {
                                "phase": "collecting",
                                "keyword": keyword,
                                "message": "扩展正在分批读取搜索结果的完整职位信息",
                            },
                        )
                    try:
                        collection = BrowserActionResponse.model_validate(
                            await browser_hub.dispatch(
                                run_id=run_id,
                                action="collect_jobs",
                                payload={
                                    "limit": batch_limit,
                                    "excludeJobIds": excluded_job_ids,
                                    "itemIntervalMs": collection_interval_ms,
                                },
                                deadline_ms=batch_deadline_ms,
                            )
                        )
                    except BrowserProtocolError as error:
                        reason = browser_protocol_error_message(error, "collect_jobs")
                        browser_errors.append(f"{keyword}：{reason}")
                        automation_repository.update_collection(
                            run_id,
                            "collecting",
                            details={
                                "phase": "collecting",
                                "currentKeyword": keyword,
                                "collectedCount": len(captured),
                                "browserErrors": browser_errors[-10:],
                                "partial": bool(captured),
                            },
                            emit_event=False,
                        )
                        automation_repository.append_event(
                            run_id,
                            "collection-batch-failed",
                            "warning",
                            {
                                "phase": "collecting",
                                "keyword": keyword,
                                "batchNumber": batch_number,
                                "collectedCount": len(captured),
                                "retainedCount": len(captured),
                                "error": reason,
                            },
                        )
                        halt_collection = True
                        break

                    raw_jobs = collection.evidence.get("jobs", [])
                    if collection.status != "success" or not isinstance(raw_jobs, list):
                        reason = collection.error or "没有读取到完整职位"
                        browser_errors.append(f"{keyword}：{reason}")
                        automation_repository.update_collection(
                            run_id,
                            "collecting",
                            details={
                                "phase": "collecting",
                                "currentKeyword": keyword,
                                "collectedCount": len(captured),
                                "browserErrors": browser_errors[-10:],
                            },
                            emit_event=False,
                        )
                        automation_repository.append_event(
                            run_id,
                            "collection-batch-finished",
                            "warning",
                            {
                                "phase": "collecting",
                                "keyword": keyword,
                                "batchNumber": batch_number,
                                "newCount": 0,
                                "collectedCount": len(captured),
                                "error": reason,
                            },
                        )
                        break

                    raw_skipped = collection.evidence.get("skipped", [])
                    if isinstance(raw_skipped, list):
                        skipped_count += len(raw_skipped)
                    new_jobs: list[CapturedJob] = []
                    for raw_job in raw_jobs:
                        try:
                            job = CapturedJob.model_validate(raw_job)
                        except ValueError as error:
                            browser_errors.append(
                                f"{keyword}：忽略无效职位数据（{error}）"
                            )
                            continue
                        if job.platform_job_id in captured:
                            continue
                        captured[job.platform_job_id] = job
                        new_jobs.append(job)
                        if len(captured) >= candidate_limit:
                            break
                    if new_jobs:
                        await run_in_threadpool(
                            job_repository.save_many, new_jobs, user_id=user_id
                        )

                    exhausted = collection.evidence.get("exhausted") is True
                    if exhausted and not new_jobs:
                        exhausted_without_new_jobs = True
                    automation_repository.update_collection(
                        run_id,
                        "collecting",
                        details={
                            "phase": "collecting",
                            "currentKeyword": keyword,
                            "collectedCount": len(captured),
                            "skippedCount": skipped_count,
                            "batchNumber": batch_number,
                            "lastBatchCount": len(new_jobs),
                            "browserErrors": browser_errors[-10:],
                        },
                        emit_event=False,
                    )
                    automation_repository.append_event(
                        run_id,
                        "collection-batch-finished",
                        "info",
                        {
                            "phase": "collecting",
                            "keyword": keyword,
                            "batchNumber": batch_number,
                            "requestedCount": batch_limit,
                            "newCount": len(new_jobs),
                            "collectedCount": len(captured),
                            "skippedCount": skipped_count,
                            "exhausted": exhausted,
                        },
                    )
                    if exhausted or not new_jobs:
                        break

                if captured:
                    automation_repository.append_event(
                        run_id,
                        "collection-keyword",
                        "info",
                        {
                            "keyword": keyword,
                            "phase": "collected",
                            "collectedCount": len(captured),
                        },
                    )

            if not captured:
                if exhausted_without_new_jobs and not browser_errors:
                    completed_at = datetime.now(UTC).isoformat()
                    no_matches_run = automation_repository.update_collection(
                        run_id,
                        "no_matches",
                        planned_jobs=[],
                        details={
                            "phase": "analysis_completed",
                            "source": "extension",
                            "attemptId": attempt_id,
                            "currentKeyword": None,
                            "candidateLimit": candidate_limit,
                            "existingExcludedCount": len(historical_job_ids),
                            "collectedCount": 0,
                            "analyzedCount": 0,
                            "approvedCount": 0,
                            "rejectedCount": 0,
                            "ruleRejectedCount": 0,
                            "duplicateCount": 0,
                            "materialErrorCount": 0,
                            "analysisErrorCount": 0,
                            "reviewedJobs": [],
                            "skippedCount": skipped_count,
                            "browserErrors": [],
                            "analysisErrors": [],
                            "outcome": "no_matches",
                            "message": (
                                "没有发现新的可采集岗位"
                                f"；已跳过本地已有 {len(historical_job_ids)} 个岗位"
                                if historical_job_ids
                                else "搜索结果中没有新的可采集岗位"
                            ),
                            "error": None,
                            "completedAt": completed_at,
                            "failedAt": None,
                        },
                    )
                    return AutomationRun.model_validate(no_matches_run)
                reason = browser_errors[-1] if browser_errors else "扩展没有采集到完整职位"
                automation_repository.update_collection(
                    run_id,
                    "failed",
                    planned_jobs=[],
                    details={
                        "phase": "failed",
                        "source": "extension",
                        "attemptId": attempt_id,
                        "currentKeyword": None,
                        "collectedCount": 0,
                        "approvedCount": 0,
                        "skippedCount": skipped_count,
                        "error": reason,
                        "failedAt": datetime.now(UTC).isoformat(),
                    },
                )
                raise HTTPException(status_code=409, detail=reason)

            planned_jobs: list[dict[str, object]] = []
            reviewed_jobs: list[dict[str, object]] = []
            rejected_count = 0
            rule_rejected_count = 0
            duplicate_count = 0
            material_error_count = 0
            analysis_error_count = 0
            analyzed_count = 0
            analysis_errors: list[str] = []

            def persist_analysis_progress() -> None:
                automation_repository.update_collection(
                    run_id,
                    "collecting",
                    details={
                        "phase": "analyzing",
                        "attemptId": attempt_id,
                        "analyzedCount": analyzed_count,
                        "approvedCount": len(planned_jobs),
                        "rejectedCount": rejected_count,
                        "ruleRejectedCount": rule_rejected_count,
                        "duplicateCount": duplicate_count,
                        "materialErrorCount": material_error_count,
                        "analysisErrorCount": analysis_error_count,
                        "reviewedJobs": reviewed_jobs,
                    },
                    emit_event=False,
                )

            def review_identity(
                job: CapturedJob, snapshot: StoredJob | None = None
            ) -> dict[str, object]:
                if snapshot is None:
                    try:
                        snapshot = job_repository.get_by_platform_job_id(
                            job.platform, job.platform_job_id, user_id=user_id
                        )
                    except KeyError:
                        snapshot = None
                return {
                    "snapshotId": snapshot.id if snapshot is not None else None,
                    "jobId": job.platform_job_id,
                    "title": snapshot.title if snapshot is not None else job.title,
                    "companyName": (
                        snapshot.company_name if snapshot is not None else job.company_name
                    ),
                    "salaryText": (
                        snapshot.salary_text if snapshot is not None else job.salary_text
                    ),
                    "location": snapshot.location if snapshot is not None else job.location,
                }

            automation_repository.update_collection(
                run_id,
                "collecting",
                details={
                    "phase": "analyzing",
                    "attemptId": attempt_id,
                    "currentKeyword": None,
                    "collectedCount": len(captured),
                    "analyzedCount": 0,
                    "approvedCount": 0,
                    "rejectedCount": 0,
                    "ruleRejectedCount": 0,
                    "duplicateCount": 0,
                    "materialErrorCount": 0,
                    "analysisErrorCount": 0,
                    "reviewedJobs": [],
                },
                emit_event=False,
            )
            automation_repository.append_event(
                run_id,
                "collection-stage-changed",
                "info",
                {
                    "phase": "analyzing",
                    "attemptId": attempt_id,
                    "collectedCount": len(captured),
                    "message": "本地服务正在逐个执行 analyze-and-plan",
                },
            )
            automation_repository.append_event(
                run_id,
                "analysis-started",
                "info",
                {
                    "phase": "analyzing",
                    "attemptId": attempt_id,
                    "collectedCount": len(captured),
                    "operation": "analyze-and-plan",
                },
            )
            for job in captured.values():
                analyzed_count += 1
                try:
                    result = await run_in_threadpool(
                        resolve_job_plan,
                        job,
                        user_id=user_id,
                        minimum_suitability_score=int(
                            config.get("minimumSuitabilityScore", 60)
                        ),
                        minimum_customization_confidence=int(
                            config.get("minimumCustomizationConfidence", 80)
                        ),
                    )
                except (HTTPException, KeyError, RuntimeError, TypeError, ValueError) as error:
                    error_text = (
                        str(error.detail)
                        if isinstance(error, HTTPException)
                        else str(error) or error.__class__.__name__
                    )
                    analysis_errors.append(f"{job.title}：{error_text}")
                    rejected_count += 1
                    analysis_error_count += 1
                    reviewed_jobs.append(
                        {
                            **review_identity(job),
                            "outcome": "analysis_error",
                            "suitabilityScore": None,
                            "reasons": [error_text],
                            "ruleMatches": [],
                        }
                    )
                    persist_analysis_progress()
                    continue

                snapshot = result.snapshot
                decision = result.match.decision
                reasons = list(decision.reasons)
                rule_matches = [
                    item.model_dump(mode="json", by_alias=True)
                    for item in decision.rule_matches
                ]
                if result.duplicate:
                    outcome = "duplicate"
                    duplicate_count += 1
                elif not decision.should_deliver:
                    outcome = "rule_rejected"
                    rule_rejected_count += 1
                elif not result.generated_greeting:
                    outcome = "material_error"
                    material_error_count += 1
                    reasons = list(dict.fromkeys([*reasons, "未生成可用问候语"]))
                else:
                    outcome = "approved"

                reviewed_jobs.append(
                    {
                        **review_identity(job, snapshot),
                        "outcome": outcome,
                        "suitabilityScore": result.match.suitability_score,
                        "reasons": reasons,
                        "ruleMatches": rule_matches,
                    }
                )
                if outcome != "approved":
                    rejected_count += 1
                    persist_analysis_progress()
                    continue

                planned_jobs.append(
                    {
                        "snapshotId": snapshot.id,
                        "jobId": snapshot.platform_job_id,
                        "url": snapshot.url,
                        "title": snapshot.title,
                        "companyName": snapshot.company_name,
                        "salaryText": snapshot.salary_text,
                        "location": snapshot.location,
                        "greeting": result.generated_greeting,
                        "suitabilityScore": result.match.suitability_score,
                        "materialStrategy": result.match.decision.material_strategy.value,
                    }
                )
                persist_analysis_progress()
                if len(planned_jobs) >= target_count:
                    break

            details = {
                "source": "extension",
                "attemptId": attempt_id,
                "collectedCount": len(captured),
                "analyzedCount": analyzed_count,
                "approvedCount": len(planned_jobs),
                "rejectedCount": rejected_count,
                "ruleRejectedCount": rule_rejected_count,
                "duplicateCount": duplicate_count,
                "materialErrorCount": material_error_count,
                "analysisErrorCount": analysis_error_count,
                "reviewedJobs": reviewed_jobs,
                "skippedCount": skipped_count,
                "browserErrors": browser_errors[-10:],
                "analysisErrors": analysis_errors[-10:],
                "currentKeyword": None,
                "completedAt": datetime.now(UTC).isoformat(),
            }
            if not planned_jobs:
                no_matches_run = automation_repository.update_collection(
                    run_id,
                    "no_matches",
                    planned_jobs=[],
                    details={
                        **details,
                        "phase": "analysis_completed",
                        "outcome": "no_matches",
                        "message": "采集与分析完成，但没有岗位通过投递规则",
                        "error": None,
                        "failedAt": None,
                    },
                )
                return AutomationRun.model_validate(no_matches_run)

            collected_run = automation_repository.update_collection(
                run_id,
                "ready",
                planned_jobs=planned_jobs,
                details={
                    **details,
                    "phase": "awaiting_confirmation",
                    "outcome": "ready",
                    "error": None,
                    "failedAt": None,
                },
            )
            automation_repository.append_event(
                run_id,
                "collection-stage-changed",
                "info",
                {
                    "phase": "awaiting_confirmation",
                    "attemptId": attempt_id,
                    "approvedCount": len(planned_jobs),
                    "message": "本地分析完成，等待页面确认企业",
                },
            )
            return AutomationRun.model_validate(collected_run)

    @router.post(
        "/jobs/{snapshot_id}/analysis",
        response_model=JobInsightResponse,
    )
    def analyze_job_snapshot(
        snapshot_id: int, request: JobInsightRequest, http_request: Request
    ) -> JobInsightResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        try:
            job = job_repository.get(snapshot_id, user_id=user_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job snapshot not found") from error

        config = automation_config()
        context, _, match = build_job_material_context(
            job,
            minimum_suitability_score=config.minimum_suitability_score,
            minimum_customization_confidence=config.minimum_customization_confidence,
            rules=config.matching_rules,
            duplicate=job.has_communicated,
        )
        if request.use_ai:
            try:
                generated = job_analysis_generator.generate(
                    context, request.model_record_id, user_id=user_id
                )
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
            return JobInsightResponse(
                job_id=job.id,
                mode="ai",
                summary=str(generated["summary"]),
                strengths=generated.get("strengths", []),
                gaps=generated.get("gaps", []),
                recommendations=generated.get("recommendations", []),
                interview_questions=generated.get("interviewQuestions", []),
                match=match,
                model_record_id=int(generated["modelRecordId"]),
                model_name=str(generated["modelName"]),
                model_id=str(generated["modelId"]),
            )

        local = build_local_job_insight(job, match)
        return JobInsightResponse(
            job_id=job.id,
            mode="local",
            summary=str(local["summary"]),
            strengths=local["strengths"],
            gaps=local["gaps"],
            recommendations=local["recommendations"],
            interview_questions=local["interviewQuestions"],
            match=match,
        )

    @router.post(
        "/jobs/{snapshot_id}/material-preview",
        response_model=MaterialPreviewResponse,
    )
    def preview_job_materials(
        snapshot_id: int, request: MaterialPreviewRequest, http_request: Request
    ) -> MaterialPreviewResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
        try:
            job = job_repository.get(snapshot_id, user_id=user_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job snapshot not found") from error
        try:
            context, default_greeting, match = build_job_material_context(
                job, user_id=user_id
            )
            generated = material_preview_generator.generate(
                context,
                request.model_record_id,
                user_id=user_id,
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
    def get_profile(http_request: Request) -> ProfilePayload:
        user = required_user(http_request)
        return ProfilePayload(data=library_repository.get_profile(user_id=int(user["id"])))

    @router.put("/profile", response_model=ProfilePayload)
    def save_profile(request: ProfilePayload, http_request: Request) -> ProfilePayload:
        user = required_user(http_request)
        profile = library_repository.save_profile(request.data, user_id=int(user["id"]))
        return ProfilePayload(data=profile)

    @router.post("/resumes/import", response_model=ResumeImportResponse, status_code=201)
    async def import_resume(
        file: Annotated[UploadFile, File()],
        http_request: Request,
        model_record_id: Annotated[int | None, Form(alias="modelRecordId")] = None,
    ) -> ResumeImportResponse:
        user = required_user(http_request)
        user_id = int(user["id"])
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
                        extract_resume,
                        parsed.resume["rawText"],
                        model_record_id,
                        user_id=user_id,
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
                        project_extractor.extract,
                        parsed.resume["rawText"],
                        model_record_id,
                        user_id=user_id,
                    )
                if extracted_projects:
                    projects = extracted_projects
                    ai_extraction_used = True
                elif not ai_profile_extracted:
                    ai_extraction_error = "模型未识别到项目，已使用本地项目标题规则降级解析"
                if ai_model_record is None:
                    models = library_repository.list("models", user_id=user_id)
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
                filename, profile, parsed.resume, projects, user_id=user_id
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        return ResumeImportResponse(
            filename=filename,
            profile_fields=sorted(imported["profile"]),
            resume_id=imported["resumeId"],
            project_ids=imported["projectIds"],
            extracted_characters=len(parsed.resume["rawText"]),
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
    def confirm_resume(resume_id: int, http_request: Request) -> ResumeConfirmationResponse:
        user = required_user(http_request)
        try:
            confirmed = library_repository.confirm_resume(resume_id, user_id=int(user["id"]))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        return ResumeConfirmationResponse(
            resume=LibraryRecord.model_validate(confirmed["resume"]),
            profile_fields=sorted(confirmed["profile"]),
            project_ids=confirmed["projectIds"],
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
    def get_default_resume_image(http_request: Request) -> FileResponse:
        user = required_user(http_request)
        try:
            return resume_image_response(
                library_repository.get_default_resume_image(user_id=int(user["id"]))
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="default resume image not found") from error

    @router.get("/resumes/{resume_id}/preview-image")
    def get_resume_preview_image(resume_id: int, http_request: Request) -> FileResponse:
        user = required_user(http_request)
        try:
            record = library_repository.get("resumes", resume_id, user_id=int(user["id"]))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        return resume_image_response(record)

    @router.put("/resumes/{resume_id}/default-image", response_model=LibraryRecord)
    def set_default_resume_image(resume_id: int, http_request: Request) -> LibraryRecord:
        user = required_user(http_request)
        try:
            return LibraryRecord(
                **library_repository.set_default_resume_image(
                    resume_id, user_id=int(user["id"])
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="resume not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/resumes/{resume_id}/extract-projects")
    async def extract_existing_resume_projects(
        resume_id: int,
        http_request: Request,
        model_record_id: Annotated[int | None, Form(alias="modelRecordId")] = None,
    ) -> dict[str, object]:
        user = required_user(http_request)
        user_id = int(user["id"])
        try:
            resume_record = library_repository.get("resumes", resume_id, user_id=user_id)
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
                project_extractor.extract, raw_text, model_record_id, user_id=user_id
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
        project_ids = library_repository.upsert_projects(projects, user_id=user_id)
        return {
            "resumeId": resume_id,
            "projectIds": project_ids,
            "projectCount": len(project_ids),
            "extractionMethod": extraction_method,
            "extractionError": extraction_error,
        }

    def valid_kind(kind: str) -> LibraryKind:
        if kind not in ALLOWED_KINDS:
            raise HTTPException(status_code=404, detail="library kind not found")
        return kind  # type: ignore[return-value]

    @router.get("/library/{kind}", response_model=LibraryListResponse)
    def list_library(kind: str, http_request: Request) -> LibraryListResponse:
        user = required_user(http_request)
        valid = valid_kind(kind)
        records = library_repository.list(valid, user_id=int(user["id"]))
        if valid == "models":
            return LibraryListResponse(items=[public_model_record(record) for record in records])
        return LibraryListResponse(items=records)

    @router.post("/library/{kind}", response_model=LibraryRecord, status_code=201)
    def create_library_record(
        kind: str, request: LibraryRecordInput, http_request: Request
    ) -> LibraryRecord:
        user = required_user(http_request)
        user_id = int(user["id"])
        valid = valid_kind(kind)
        if valid == "models":
            validate_model_data(request.data)
            return public_model_record(
                library_repository.create(valid, request.name, request.data, user_id=user_id)
            )
        record = LibraryRecord.model_validate(
            library_repository.create(valid, request.name, request.data, user_id=user_id)
        )
        return record

    @router.put("/library/{kind}/{record_id}", response_model=LibraryRecord)
    def update_library_record(
        kind: str, record_id: int, request: LibraryRecordInput, http_request: Request
    ) -> LibraryRecord:
        user = required_user(http_request)
        user_id = int(user["id"])
        try:
            valid = valid_kind(kind)
            data = request.data
            if valid == "models":
                existing = library_repository.get(valid, record_id, user_id=user_id)
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
            result = library_repository.update(
                valid, record_id, request.name, data, user_id=user_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="record not found") from error
        if valid == "models":
            return public_model_record(result)
        record = LibraryRecord.model_validate(result)
        return record

    @router.delete("/library/{kind}/{record_id}", status_code=204)
    def delete_library_record(kind: str, record_id: int, http_request: Request) -> Response:
        user = required_user(http_request)
        valid = valid_kind(kind)
        if not library_repository.delete(valid, record_id, user_id=int(user["id"])):
            raise HTTPException(status_code=404, detail="record not found")
        return Response(status_code=204)

    @router.post("/library/models/{record_id}/test")
    def test_model_connection(record_id: int, http_request: Request) -> dict[str, object]:
        user = required_user(http_request)
        user_id = int(user["id"])
        try:
            record = library_repository.get("models", record_id, user_id=user_id)
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
        library_repository.update("models", record_id, record["name"], data, user_id=user_id)
        return result

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
