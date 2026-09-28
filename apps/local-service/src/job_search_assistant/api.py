from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from . import __version__
from .domain import (
    DecisionRequest,
    DecisionResponse,
    JdAnalysisRequest,
    JdAnalysisResponse,
    analyze_jd,
    evaluate_material_strategy,
)
from .domain.models import (
    HealthResponse,
    JobCaptureRequest,
    JobCaptureResponse,
    JobEvaluationRequest,
    JobEvaluationResponse,
    JobListResponse,
    LibraryListResponse,
    LibraryRecord,
    LibraryRecordInput,
    ProfilePayload,
    RagRebuildResponse,
    RagSearchRequest,
    RagSearchResponse,
    RagStatus,
    RiskRuleInput,
)
from .rag import RagService
from .repositories import JobRepository, LibraryRepository
from .repositories.library import ALLOWED_KINDS, LibraryKind
from .resume_pdf import build_resume_pdf
from .resume_templates import RESUME_TEMPLATES, SAMPLE_RESUME, TEAL_PROFESSIONAL_ID


def create_router(
    job_repository: JobRepository,
    library_repository: LibraryRepository,
    rag_service: RagService,
) -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @router.post("/decisions/evaluate", response_model=DecisionResponse)
    def evaluate_decision(request: DecisionRequest) -> DecisionResponse:
        return evaluate_material_strategy(request)

    @router.post("/jobs/capture", response_model=JobCaptureResponse)
    def capture_jobs(request: JobCaptureRequest) -> JobCaptureResponse:
        job_ids = job_repository.save_many(request.jobs)
        return JobCaptureResponse(accepted=len(job_ids), job_ids=job_ids)

    @router.get("/jobs", response_model=JobListResponse)
    def list_jobs(limit: int = Query(default=100, ge=1, le=500)) -> JobListResponse:
        return JobListResponse(
            total=job_repository.count(),
            items=job_repository.list_recent(limit),
        )

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

    @router.get("/profile", response_model=ProfilePayload)
    def get_profile() -> ProfilePayload:
        return ProfilePayload(data=library_repository.get_profile())

    @router.put("/profile", response_model=ProfilePayload)
    def save_profile(request: ProfilePayload) -> ProfilePayload:
        return ProfilePayload(data=library_repository.save_profile(request.data))

    def valid_kind(kind: str) -> LibraryKind:
        if kind not in ALLOWED_KINDS:
            raise HTTPException(status_code=404, detail="library kind not found")
        return kind  # type: ignore[return-value]

    @router.get("/library/{kind}", response_model=LibraryListResponse)
    def list_library(kind: str) -> LibraryListResponse:
        return LibraryListResponse(items=library_repository.list(valid_kind(kind)))

    @router.post("/library/{kind}", response_model=LibraryRecord, status_code=201)
    def create_library_record(kind: str, request: LibraryRecordInput) -> LibraryRecord:
        return LibraryRecord.model_validate(
            library_repository.create(valid_kind(kind), request.name, request.data)
        )

    @router.put("/library/{kind}/{record_id}", response_model=LibraryRecord)
    def update_library_record(
        kind: str, record_id: int, request: LibraryRecordInput
    ) -> LibraryRecord:
        try:
            result = library_repository.update(
                valid_kind(kind), record_id, request.name, request.data
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="record not found") from error
        return LibraryRecord.model_validate(result)

    @router.delete("/library/{kind}/{record_id}", status_code=204)
    def delete_library_record(kind: str, record_id: int) -> Response:
        if not library_repository.delete(valid_kind(kind), record_id):
            raise HTTPException(status_code=404, detail="record not found")
        return Response(status_code=204)

    @router.get("/rag/status", response_model=RagStatus)
    def rag_status() -> RagStatus:
        return RagStatus.model_validate(rag_service.status())

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

    @router.get("/resume-templates/{template_id}/sample.pdf")
    def download_sample_resume(template_id: str) -> StreamingResponse:
        if template_id != TEAL_PROFESSIONAL_ID:
            raise HTTPException(status_code=404, detail="resume template not found")
        pdf = build_resume_pdf(SAMPLE_RESUME)
        return StreamingResponse(
            BytesIO(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": ('inline; filename="job-search-assistant-sample-resume.pdf"')
            },
        )

    return router
