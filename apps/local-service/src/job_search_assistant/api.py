import hashlib
import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated
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
from fastapi.responses import HTMLResponse, StreamingResponse
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
    CapturedJob,
    ClientLogInput,
    ClientLogListResponse,
    ClientLogRecord,
    DeliveryListResponse,
    DeliveryRecord,
    DeliveryRecordInput,
    HealthResponse,
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
    ProfilePayload,
    RagChunkListResponse,
    RagRebuildResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagStatus,
    ResumeImportResponse,
    RiskRuleInput,
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
from .resume_import import MAX_RESUME_BYTES, extract_projects_from_text, parse_resume
from .resume_pdf import build_resume_pdf
from .resume_templates import RESUME_TEMPLATES, SAMPLE_RESUME, TEAL_PROFESSIONAL_ID

logger = logging.getLogger("job_search_assistant.client")


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
) -> APIRouter:
    router = APIRouter(prefix="/v1")
    greeting_generation_ids: set[int] = set()
    greeting_generation_lock = Lock()

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
    ) -> tuple[dict[str, object], str, AutomaticJobMatchResponse]:
        match_request = AutomaticJobMatchRequest(
            title=job.title,
            job_text=job.description,
            skills=job.skills,
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
        resumes = library_repository.list("resumes")
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
    def list_jobs(limit: int = Query(default=100, ge=1, le=500)) -> JobListResponse:
        return JobListResponse(
            total=job_repository.count(),
            items=job_repository.list_recent(limit),
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
            parsed = parse_resume(filename, await file.read(MAX_RESUME_BYTES + 1))
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

        rebuilt = False
        indexed_chunks = None
        index_error = None
        try:
            index_result = rag_service.rebuild()
            rebuilt = True
            indexed_chunks = index_result["rebuilt"]
        except RuntimeError as error:
            index_error = str(error)
        return ResumeImportResponse(
            filename=filename,
            profile_fields=sorted(imported["profile"]),
            resume_id=imported["resumeId"],
            project_ids=imported["projectIds"],
            extracted_characters=len(parsed.resume["rawText"]),
            index_rebuilt=rebuilt,
            indexed_chunks=indexed_chunks,
            index_error=index_error,
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
            return model_tester.test(record["data"])
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

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
