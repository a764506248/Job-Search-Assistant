from fastapi import APIRouter

from . import __version__
from .domain import DecisionRequest, DecisionResponse, evaluate_material_strategy
from .domain.models import HealthResponse, JobCaptureRequest, JobCaptureResponse
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

    return router
