from fastapi import APIRouter

from . import __version__
from .domain import DecisionRequest, DecisionResponse, evaluate_material_strategy
from .domain.models import HealthResponse

router = APIRouter(prefix="/v1")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@router.post("/decisions/evaluate", response_model=DecisionResponse)
def evaluate_decision(request: DecisionRequest) -> DecisionResponse:
    return evaluate_material_strategy(request)
