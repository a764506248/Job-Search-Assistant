from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from ..domain.models import ApiModel


class PlatformOption(ApiModel):
    label: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=100)


class DeliveryConfigInput(ApiModel):
    name: str = Field(default="默认手机投递", min_length=1, max_length=100)
    is_default: bool = True
    enabled: bool = True
    source_tabs: list[Literal["推荐", "附近", "最新"]] = Field(
        default_factory=lambda: ["推荐", "附近", "最新"], min_length=1
    )
    job_intentions: list[PlatformOption] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    city_code: str | None = Field(default=None, max_length=100)
    city_name: str | None = Field(default=None, max_length=100)
    experience: list[PlatformOption] = Field(default_factory=list)
    degree: list[PlatformOption] = Field(default_factory=list)
    company_scale: list[PlatformOption] = Field(default_factory=list)
    boss_activity: PlatformOption | None = None
    salary_mode: Literal["all", "preset", "custom"] = "all"
    salary_code: str | None = Field(default=None, max_length=100)
    salary_min_k: int | None = Field(default=None, ge=0, le=1000)
    salary_max_k: int | None = Field(default=None, ge=0, le=1000)
    benefits: list[PlatformOption] = Field(default_factory=list)
    financing: list[PlatformOption] = Field(default_factory=list)
    industries: list[PlatformOption] = Field(default_factory=list)
    recommended_tags: list[PlatformOption] = Field(default_factory=list)
    target_delivery_count: int = Field(default=1, ge=1, le=100)
    max_scan_count: int = Field(default=20, ge=1, le=1000)
    interval_seconds: float = Field(default=2, ge=1, le=60)
    minimum_score: int = Field(default=60, ge=0, le=100)
    minimum_customization_confidence: int = Field(default=50, ge=0, le=100)
    resume_id: int | None = None
    send_resume: bool = False
    greeting_strategy: Literal["custom", "default"] = "custom"
    fallback_greeting: str = Field(
        default="您好，我对贵司的这个岗位很感兴趣，希望有机会进一步沟通，谢谢。",
        max_length=2000,
    )
    confirmation_mode: Literal["automatic", "per_job"] = "automatic"
    stop_on_uncertain: bool = True

    @model_validator(mode="after")
    def validate_plan(self) -> DeliveryConfigInput:
        if self.max_scan_count < self.target_delivery_count:
            raise ValueError("最大扫描数不能小于目标投递数")
        if self.salary_mode == "custom":
            if self.salary_min_k is None or self.salary_max_k is None:
                raise ValueError("自定义薪资需要填写最低和最高薪资")
            if self.salary_min_k > self.salary_max_k:
                raise ValueError("最低薪资不能高于最高薪资")
        return self


class AgentKeyCreate(ApiModel):
    name: str = Field(default="Codex", min_length=1, max_length=100)
    scopes: list[Literal["agent:read", "agent:run"]] = Field(
        default_factory=lambda: ["agent:read", "agent:run"], min_length=1
    )
    expires_in_days: int | None = Field(default=90, ge=1, le=365)
    base_url: str | None = Field(default=None, max_length=255)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None  # 兼容旧客户端：不带地址的 Key 仍可创建和使用。
        candidate = value.strip()
        parsed = urlsplit(candidate)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("服务地址端口无效") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(char.isspace() for char in candidate)
        ):
            raise ValueError("服务地址必须是不含账号、路径、查询或片段的 http(s) 站点地址")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("服务地址端口无效")
        return f"{parsed.scheme}://{parsed.netloc}"


class AgentRunCreate(ApiModel):
    config_id: int | None = None


class JobCheckInput(ApiModel):
    platform_job_id: str = Field(min_length=1, max_length=300)
    source_tab: str = Field(default="推荐", max_length=30)
    list_position: int | None = Field(default=None, ge=1)


class JobCaptureInput(ApiModel):
    platform_job_id: str = Field(min_length=1, max_length=300)
    source_tab: str = Field(default="推荐", max_length=30)
    list_position: int | None = Field(default=None, ge=1)
    snapshot: dict[str, Any]


class JobPrepareInput(ApiModel):
    platform_job_id: str = Field(min_length=1, max_length=300)
    observed_title: str = Field(min_length=1, max_length=300)
    observed_company_name: str = Field(min_length=1, max_length=300)
    user_confirmed: bool = False


class JobResultInput(ApiModel):
    outcome: Literal["delivered", "skipped", "failed", "uncertain"]
    idempotency_key: str = Field(min_length=8, max_length=200)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = Field(default=None, max_length=2000)


class RunFinishInput(ApiModel):
    status: Literal["completed", "stopped", "failed", "uncertain"] = "completed"
    reason: str | None = Field(default=None, max_length=2000)
