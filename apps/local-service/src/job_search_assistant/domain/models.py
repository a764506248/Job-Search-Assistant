from enum import StrEnum

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
