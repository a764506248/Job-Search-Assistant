from fastapi import APIRouter, HTTPException, Query, Response, status

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
    RiskRuleInput,
)
from .repositories import JobRepository


def create_router(job_repository: JobRepository) -> APIRouter:
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

    return router
