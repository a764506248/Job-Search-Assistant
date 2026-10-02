from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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


SetupCheckStatus = Literal["ready", "pending", "warning", "blocked"]


class SetupCheck(ApiModel):
    key: str
    label: str
    status: SetupCheckStatus
    message: str
    blocking: bool = False
    action_label: str | None = None
    action_path: str | None = None


class SetupStatusResponse(ApiModel):
    overall: SetupCheckStatus
    completed: int
    total: int
    checks: list[SetupCheck]
    checked_at: datetime


class ClientLogInput(ApiModel):
    source: Literal["extension-content", "extension-background", "extension-page"]
    level: Literal["warning", "error"] = "error"
    event: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    page_url: str | None = Field(default=None, max_length=1000)
    platform_job_id: str | None = Field(default=None, max_length=200)
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class ClientLogRecord(ClientLogInput):
    id: int
    received_at: datetime


class ClientLogListResponse(ApiModel):
    items: list[ClientLogRecord]


class CapturedJob(ApiModel):
    platform: Literal["boss"]
    platform_job_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    company_size: str | None = None
    location: str | None = None
    work_address: str | None = None
    salary_text: str | None = None
    experience: str | None = None
    education: str | None = None
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    recruiter_name: str | None = None
    recruiter_title: str | None = None
    has_communicated: bool = False
    has_interview: bool = False
    generated_greeting: str | None = Field(default=None, max_length=2000)
    resume_variant: Literal["default", "optimized"] = "default"
    generated_resume_id: int | None = None
    resume_optimization: str | None = Field(default=None, max_length=5000)
    captured_at: datetime
    source: Literal["dom", "page-state", "manual"]


class ManualJobInput(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    company_name: str = Field(min_length=1, max_length=300)
    company_size: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    work_address: str | None = Field(default=None, max_length=500)
    salary_text: str | None = Field(default=None, max_length=100)
    experience: str | None = Field(default=None, max_length=100)
    education: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list, max_length=100)
    recruiter_name: str | None = Field(default=None, max_length=200)
    recruiter_title: str | None = Field(default=None, max_length=200)
    has_communicated: bool = False
    has_interview: bool = False
    generated_greeting: str | None = Field(default=None, max_length=2000)
    resume_variant: Literal["default", "optimized"] = "default"
    generated_resume_id: int | None = None
    resume_optimization: str | None = Field(default=None, max_length=5000)


class JobTrackingUpdate(ApiModel):
    has_communicated: bool
    has_interview: bool
    generated_greeting: str | None = Field(default=None, max_length=2000)
    resume_variant: Literal["default", "optimized"] = "default"
    generated_resume_id: int | None = None
    resume_optimization: str | None = Field(default=None, max_length=5000)


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
    page: int
    page_size: int
    total_pages: int
    items: list[StoredJob]


class DeliveryRecordInput(ApiModel):
    platform: Literal["boss"] = "boss"
    platform_job_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    company_name: str = Field(min_length=1, max_length=300)
    salary_text: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    recruiter_name: str | None = Field(default=None, max_length=200)
    status: Literal[
        "delivered", "greeting_sent", "failed", "skipped", "blocked", "fatal_limit"
    ]
    decision: str | None = Field(default=None, max_length=50)
    reason: str | None = Field(default=None, max_length=2000)
    greeting_text: str | None = Field(default=None, max_length=2000)
    detail: str | None = Field(default=None, max_length=2000)
    applied_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryRecord(DeliveryRecordInput):
    id: int
    created_at: datetime
    updated_at: datetime


class DeliveryListResponse(ApiModel):
    total: int
    items: list[DeliveryRecord]


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


class AutomaticJobMatchRequest(ApiModel):
    job_text: str = Field(min_length=1)
    title: str = ""
    skills: list[str] = Field(default_factory=list)
    minimum_suitability_score: int = Field(default=75, ge=0, le=100)
    minimum_customization_confidence: int = Field(default=80, ge=0, le=100)
    rules: list[RiskRuleInput] = Field(default_factory=list)
    elite_school_action: RuleAction = RuleAction.USE_DEFAULT_MATERIALS
    duplicate: bool = False
    company_blocked: bool = False


class LibraryRecordInput(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)


class LibraryRecord(LibraryRecordInput):
    id: int
    kind: str
    created_at: datetime
    updated_at: datetime


class LibraryListResponse(ApiModel):
    items: list[LibraryRecord]


class ProfilePayload(ApiModel):
    data: dict[str, Any] = Field(default_factory=dict)


class ResumeImportResponse(ApiModel):
    filename: str
    profile_fields: list[str]
    resume_id: int
    project_ids: list[int]
    extracted_characters: int
    index_rebuilt: bool
    indexed_chunks: int | None = None
    index_error: str | None = None
    ai_extraction_used: bool
    ai_project_count: int = 0
    ai_extraction_error: str | None = None
    ai_model_record_id: int | None = None
    ai_model_name: str | None = None
    ai_model_id: str | None = None
    ai_attempt_errors: list[str] = Field(default_factory=list)
    ai_profile_extracted: bool = False


class RagStatus(ApiModel):
    chunks: int
    sources: int
    indexed_at: datetime | None = None
    model: str | None = None
    embedding_available: bool
    embedding_service: dict[str, Any]


class RagRebuildResponse(ApiModel):
    chunks: int
    sources: int
    indexed_at: datetime | None = None
    model: str | None = None
    rebuilt: int


class RagSearchRequest(ApiModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class RagSearchResult(ApiModel):
    source_type: str
    source_id: str
    source_name: str
    knowledge_type: str = ""
    entity_id: str = ""
    tags: list[str] = Field(default_factory=list)
    chunk_index: int
    content: str
    score: float
    vector_score: float = 0
    keyword_score: float = 0


class AutomaticJobMatchResponse(ApiModel):
    analysis: JdAnalysisResponse
    suitability_score: int
    customization_confidence: int
    decision: DecisionResponse
    evidence: list[RagSearchResult]
    scoring_version: str = "local-hybrid-v1"


class AutomationConfigResponse(ApiModel):
    target_roles: list[str] = Field(default_factory=list)
    target_cities: list[str] = Field(default_factory=list)
    city_code: str = ""
    search_keywords: list[str] = Field(default_factory=list)
    minimum_salary_k: int = Field(default=20, ge=0)
    daily_target: int = Field(default=20, ge=1, le=500)
    minimum_suitability_score: int = Field(default=60, ge=0, le=100)
    minimum_customization_confidence: int = Field(default=80, ge=0, le=100)
    send_resume_image: bool = False
    default_greeting: str = ""
    default_resume_image_available: bool = False
    matching_rules: list[RiskRuleInput] = Field(default_factory=list)


class JobAnalysisPlanRequest(ApiModel):
    job: CapturedJob
    minimum_suitability_score: int | None = Field(default=None, ge=0, le=100)
    minimum_customization_confidence: int | None = Field(default=None, ge=0, le=100)
    company_blocked: bool = False


class JobAnalysisPlanResponse(ApiModel):
    snapshot: StoredJob
    match: AutomaticJobMatchResponse
    generated_greeting: str | None = None
    default_resume_image_available: bool = False
    duplicate: bool = False


class MaterialPreviewRequest(ApiModel):
    model_record_id: int | None = None


class ResumeCompositionPreview(ApiModel):
    headline: str
    summary: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    work_experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    optimization_notes: list[str] = Field(default_factory=list)


class MaterialPreviewResponse(ApiModel):
    job_id: int
    model_record_id: int
    model_name: str
    model_id: str
    default_greeting: str
    greeting: str
    resume: ResumeCompositionPreview
    match: AutomaticJobMatchResponse


class RagSearchResponse(ApiModel):
    items: list[RagSearchResult]


class RagChunk(ApiModel):
    id: int
    source_type: str
    source_id: str
    source_name: str
    knowledge_type: str = ""
    entity_id: str = ""
    tags: list[str] = Field(default_factory=list)
    chunk_index: int
    content: str
    content_hash: str
    embedding: list[float]
    dimensions: int
    model: str
    indexed_at: datetime


class RagChunkListResponse(ApiModel):
    total: int
    items: list[RagChunk]
