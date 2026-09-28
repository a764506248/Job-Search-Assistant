from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class MaterialStrategy(StrEnum):
    CUSTOM = "custom"
    DEFAULT = "default"
    BLOCKED = "blocked"


class RuleAction(StrEnum):
    NOTIFY = "notify"
    REDUCE_SCORE = "reduce_score"
    USE_DEFAULT_MATERIALS = "use_default_materials"
    BLOCK_DELIVERY = "block_delivery"


class RiskRuleInput(ApiModel):
    id: str
    name: str
    patterns: list[str] = Field(min_length=1)
    action: RuleAction
    score_penalty: int = Field(default=0, ge=0, le=100)
    enabled: bool = True


class RuleMatch(ApiModel):
    rule_id: str
    rule_name: str
    action: RuleAction
    evidence: list[str]


class DecisionRequest(ApiModel):
    job_text: str = Field(min_length=1)
    suitability_score: int = Field(ge=0, le=100)
    customization_confidence: int = Field(ge=0, le=100)
    minimum_suitability_score: int = Field(default=75, ge=0, le=100)
    minimum_customization_confidence: int = Field(default=80, ge=0, le=100)
    rules: list[RiskRuleInput] = Field(default_factory=list)
    duplicate: bool = False
    company_blocked: bool = False

    @model_validator(mode="after")
    def normalize_job_text(self) -> "DecisionRequest":
        self.job_text = self.job_text.strip()
        if not self.job_text:
            raise ValueError("job_text must not be blank")
        return self


class DecisionResponse(ApiModel):
    material_strategy: MaterialStrategy
    should_deliver: bool
    effective_suitability_score: int
    reasons: list[str]
    rule_matches: list[RuleMatch]


class HealthResponse(ApiModel):
    status: str = "ok"
    service: str = "job-search-assistant-local"
    version: str


class CapturedJob(ApiModel):
    platform: Literal["boss"]
    platform_job_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    location: str | None = None
    salary_text: str | None = None
    experience: str | None = None
    education: str | None = None
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    recruiter_name: str | None = None
    recruiter_title: str | None = None
    captured_at: datetime
    source: Literal["dom", "page-state"]


class JobCaptureRequest(ApiModel):
    jobs: list[CapturedJob] = Field(min_length=1, max_length=100)


class JobCaptureResponse(ApiModel):
    accepted: int
    job_ids: list[str]


class StoredJob(CapturedJob):
    id: int
    content_hash: str


class JobListResponse(ApiModel):
    total: int
    items: list[StoredJob]


class RequirementLevel(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    NEUTRAL = "neutral"
    NEGATED = "negated"
    CONTEXT = "context"


class RequirementCategory(StrEnum):
    ELITE_SCHOOL = "elite_school"
    EDUCATION_DEGREE = "education_degree"


class TextEvidence(ApiModel):
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "TextEvidence":
        if self.end < self.start:
            raise ValueError("evidence end must be greater than or equal to start")
        return self


class ParsedRequirement(ApiModel):
    category: RequirementCategory
    level: RequirementLevel
    normalized_value: str
    evidence: TextEvidence
    explanation: str


class JdAnalysisRequest(ApiModel):
    job_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_job_text(self) -> "JdAnalysisRequest":
        self.job_text = self.job_text.strip()
        if not self.job_text:
            raise ValueError("job_text must not be blank")
        return self


class JdAnalysisResponse(ApiModel):
    requirements: list[ParsedRequirement]
    risk_requirements: list[ParsedRequirement]
    has_risk_signals: bool
    parser_version: str


class JobEvaluationRequest(DecisionRequest):
    elite_school_action: RuleAction = RuleAction.NOTIFY


class JobEvaluationResponse(ApiModel):
    analysis: JdAnalysisResponse
    decision: DecisionResponse
