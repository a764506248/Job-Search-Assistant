from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ..auth_token import verify_token
from ..domain import build_automatic_match
from ..domain.models import (
    AutomaticJobMatchRequest,
    CapturedJob,
    DeliveryRecordInput,
    RiskRuleInput,
    RuleAction,
)
from ..knowledge import KnowledgeSearchService
from ..project_extraction import GreetingGenerator
from ..repositories import (
    AuthRepository,
    DeliveryRepository,
    JobRepository,
    LibraryRepository,
)
from .eligibility import (
    education_block_reason,
    incomplete_title_reason,
    missing_linux_evidence_reason,
)
from .models import (
    AgentKeyCreate,
    AgentRunCreate,
    DeliveryConfigInput,
    JobCaptureInput,
    JobCheckInput,
    JobPrepareInput,
    JobResultInput,
    RunFinishInput,
)
from .repository import CodexDeliveryRepository


def create_codex_delivery_router(
    repository: CodexDeliveryRepository,
    auth_repository: AuthRepository,
    library_repository: LibraryRepository,
    knowledge_search: KnowledgeSearchService,
    job_repository: JobRepository,
    delivery_repository: DeliveryRepository,
    greeting_generator: GreetingGenerator,
) -> APIRouter:
    router = APIRouter(prefix="/v1")

    def web_user(request: Request) -> dict[str, Any]:
        authorization = request.headers.get("Authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        claims = verify_token(authorization[7:].strip())
        if not claims:
            raise HTTPException(status_code=401, detail="登录已失效")
        try:
            user = auth_repository.get_user(int(claims["sub"]))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=401, detail="登录已失效") from error
        if not user.get("isActive"):
            raise HTTPException(status_code=403, detail="账号不可用")
        return user

    def agent_identity(request: Request, scope: str = "agent:read") -> dict[str, Any]:
        authorization = request.headers.get("Authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="缺少 Agent Key")
        key = repository.authenticate_key(authorization[7:].strip(), scope)
        if key is None:
            raise HTTPException(status_code=401, detail="Agent Key 无效、已过期或权限不足")
        try:
            user = auth_repository.get_user(int(key["userId"]))
        except KeyError as error:
            raise HTTPException(status_code=401, detail="Agent Key 用户不存在") from error
        if not user.get("isActive"):
            raise HTTPException(status_code=403, detail="账号不可用")
        return {"key": key, "user": user}

    def get_run_or_404(run_id: int, user_id: int, *, steps: bool = False) -> dict[str, Any]:
        try:
            return repository.get_run(run_id, user_id=user_id, include_steps=steps)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Codex 投递任务不存在") from error

    def validate_resume(payload: DeliveryConfigInput, user_id: int) -> None:
        if payload.resume_id is None:
            return
        try:
            library_repository.get("resumes", payload.resume_id, user_id=user_id)
        except KeyError as error:
            raise HTTPException(status_code=422, detail="所选简历不存在或不属于当前账号") from error

    @router.get("/agent-keys")
    def list_agent_keys(request: Request) -> dict[str, Any]:
        user = web_user(request)
        return {"items": repository.list_keys(int(user["id"]))}

    @router.post("/agent-keys", status_code=status.HTTP_201_CREATED)
    def create_agent_key(payload: AgentKeyCreate, request: Request) -> dict[str, Any]:
        user = web_user(request)
        key, plaintext = repository.create_key(
            int(user["id"]), payload.name, payload.scopes, payload.expires_in_days
        )
        return {"key": key, "plaintext": plaintext}

    @router.delete("/agent-keys/{key_id}")
    def revoke_agent_key(key_id: int, request: Request) -> dict[str, Any]:
        user = web_user(request)
        try:
            return {"key": repository.revoke_key(key_id, user_id=int(user["id"]))}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Agent Key 不存在") from error

    @router.get("/codex-delivery/configs")
    def list_configs(request: Request) -> dict[str, Any]:
        user = web_user(request)
        return {"items": repository.list_configs(int(user["id"]))}

    @router.post("/codex-delivery/configs", status_code=status.HTTP_201_CREATED)
    def create_config(payload: DeliveryConfigInput, request: Request) -> dict[str, Any]:
        user = web_user(request)
        user_id = int(user["id"])
        validate_resume(payload, user_id)
        return repository.save_config(user_id, payload.model_dump(by_alias=False))

    @router.put("/codex-delivery/configs/{config_id}")
    def update_config(
        config_id: int, payload: DeliveryConfigInput, request: Request
    ) -> dict[str, Any]:
        user = web_user(request)
        try:
            validate_resume(payload, int(user["id"]))
            return repository.save_config(
                int(user["id"]), payload.model_dump(by_alias=False), config_id=config_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="配置不存在") from error

    @router.delete("/codex-delivery/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_config(config_id: int, request: Request) -> None:
        user = web_user(request)
        try:
            repository.delete_config(config_id, user_id=int(user["id"]))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="配置不存在") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/codex-delivery/runs")
    def list_web_runs(request: Request) -> dict[str, Any]:
        user = web_user(request)
        return {"items": repository.list_runs(int(user["id"]))}

    @router.get("/codex-delivery/runs/{run_id}")
    def get_web_run(run_id: int, request: Request) -> dict[str, Any]:
        user = web_user(request)
        return get_run_or_404(run_id, int(user["id"]), steps=True)

    @router.get("/agent/me")
    def agent_me(request: Request) -> dict[str, Any]:
        identity = agent_identity(request)
        return {
            "user": {
                "id": identity["user"]["id"],
                "username": identity["user"]["username"],
            },
            "key": {
                "id": identity["key"]["id"],
                "name": identity["key"]["name"],
                "scopes": identity["key"]["scopes"],
            },
        }

    @router.get("/agent/context")
    def agent_context(request: Request) -> dict[str, Any]:
        identity = agent_identity(request)
        user_id = int(identity["user"]["id"])
        return {
            "profile": library_repository.get_profile(user_id=user_id),
            "projects": library_repository.list("projects", user_id=user_id),
            "resumes": library_repository.list("resumes", user_id=user_id),
            "rules": library_repository.list("rules", user_id=user_id),
            "targets": library_repository.list("targets", user_id=user_id),
        }

    @router.get("/agent/configs/default")
    def agent_default_config(request: Request) -> dict[str, Any]:
        identity = agent_identity(request)
        config = repository.default_config(int(identity["user"]["id"]))
        if config is None:
            raise HTTPException(status_code=404, detail="尚未创建 Codex 投递配置")
        return config

    @router.post("/agent/runs", status_code=status.HTTP_201_CREATED)
    def create_agent_run(payload: AgentRunCreate, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        try:
            config = (
                repository.get_config(payload.config_id, user_id=user_id)
                if payload.config_id is not None
                else repository.default_config(user_id)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="配置不存在") from error
        if config is None or not config["enabled"]:
            raise HTTPException(status_code=409, detail="没有可用的 Codex 投递配置")
        return repository.create_run(user_id, config)

    @router.get("/agent/runs/{run_id}")
    def get_agent_run(run_id: int, request: Request) -> dict[str, Any]:
        identity = agent_identity(request)
        return get_run_or_404(run_id, int(identity["user"]["id"]), steps=True)

    @router.post("/agent/runs/{run_id}/jobs/check")
    def check_job(run_id: int, payload: JobCheckInput, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        get_run_or_404(run_id, user_id)
        try:
            step, created = repository.check_job(
                user_id, run_id, payload.platform_job_id, payload.source_tab, payload.list_position
            )
            return {"duplicate": not created, "step": step}
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/agent/runs/{run_id}/jobs/capture")
    def capture_job(run_id: int, payload: JobCaptureInput, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        get_run_or_404(run_id, user_id)
        required = ("title", "companyName", "description")
        missing = [field for field in required if not str(payload.snapshot.get(field, "")).strip()]
        if missing:
            raise HTTPException(status_code=422, detail=f"岗位快照缺少字段：{', '.join(missing)}")
        try:
            step, _ = repository.check_job(
                user_id,
                run_id,
                payload.platform_job_id,
                payload.source_tab,
                payload.list_position,
            )
            saved = repository.capture_job(user_id, run_id, int(step["id"]), payload.snapshot)
            pc_job_id = f"codex-phone:{payload.platform_job_id}"
            snapshot = payload.snapshot
            captured = CapturedJob(
                platform="boss",
                platform_job_id=pc_job_id,
                url=f"codex-phone://run/{run_id}/job/{step['id']}",
                title=str(snapshot["title"]).strip(),
                company_name=str(snapshot["companyName"]).strip(),
                company_size=_optional_text(snapshot.get("companySize")),
                location=_optional_text(snapshot.get("location")),
                work_address=_optional_text(snapshot.get("workAddress")),
                salary_text=_optional_text(snapshot.get("salaryText")),
                experience=_optional_text(snapshot.get("experience")),
                education=_optional_text(snapshot.get("education")),
                description=str(snapshot["description"]).strip(),
                skills=_string_list(snapshot.get("skills")),
                recruiter_name=_optional_text(snapshot.get("recruiterName")),
                recruiter_title=_optional_text(snapshot.get("recruiterTitle")),
                recruiter_active_text=_optional_text(snapshot.get("recruiterActiveText")),
                captured_at=datetime.now(UTC),
                source="codex-phone",
            )
            job_repository.save_many([captured], user_id=user_id)
            pc_snapshot = job_repository.get_by_platform_job_id(
                "boss", pc_job_id, user_id=user_id
            )
            return repository.link_job_snapshot(user_id, run_id, int(saved["id"]), pc_snapshot.id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/agent/runs/{run_id}/jobs/{step_id}/prepare")
    def prepare_job(
        run_id: int, step_id: int, payload: JobPrepareInput, request: Request
    ) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        get_run_or_404(run_id, user_id)
        try:
            return repository.prepare_job(
                user_id,
                run_id,
                step_id,
                payload.platform_job_id,
                payload.observed_title,
                payload.observed_company_name,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="岗位步骤不存在") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/agent/runs/{run_id}/jobs/{step_id}/analyze")
    def analyze_job(run_id: int, step_id: int, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        run = get_run_or_404(run_id, user_id)
        try:
            step = repository.get_step(step_id, user_id=user_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="岗位步骤不存在") from error
        if step["runId"] != run_id or step["status"] != "captured":
            raise HTTPException(status_code=409, detail="岗位尚未采集或已经分析")
        snapshot = step["snapshot"] or {}
        query = "\n".join(
            str(value)
            for value in (
                snapshot.get("title"),
                " ".join(snapshot.get("skills", [])),
                snapshot.get("description"),
            )
            if value
        )
        rules = _matching_rules(library_repository, user_id)
        evidence = knowledge_search.search(query, 8, user_id=user_id)
        match = build_automatic_match(
            AutomaticJobMatchRequest(
                title=str(snapshot.get("title", "")),
                job_text=str(snapshot.get("description", "")),
                skills=[str(item) for item in snapshot.get("skills", [])],
                minimum_suitability_score=int(run["configSnapshot"]["minimumScore"]),
                minimum_customization_confidence=int(
                    run["configSnapshot"]["minimumCustomizationConfidence"]
                ),
                rules=rules,
            ),
            evidence,
        )
        profile = library_repository.get_profile(user_id=user_id)
        resumes = library_repository.list("resumes", user_id=user_id)
        selected_resume = next(
            (item for item in resumes if item["id"] == run["configSnapshot"].get("resumeId")),
            None,
        )
        materials = [profile, library_repository.list("projects", user_id=user_id), resumes]
        block_reasons = [
            reason
            for reason in (
                education_block_reason(snapshot, profile, selected_resume),
                incomplete_title_reason(snapshot),
                missing_linux_evidence_reason(snapshot, materials),
            )
            if reason
        ]
        if match.suitability_score < run["configSnapshot"]["minimumScore"]:
            block_reasons.append("岗位适合度未达 Codex 投递阈值")
        if (
            match.customization_confidence
            < run["configSnapshot"]["minimumCustomizationConfidence"]
        ):
            block_reasons.append("材料定制可信度未达 Codex 投递阈值")
        if block_reasons:
            decision = match.decision.model_copy(
                update={
                    "should_deliver": False,
                    "reasons": [*match.decision.reasons, *block_reasons],
                }
            )
            match = match.model_copy(update={"decision": decision})
        pc_job_id = f"codex-phone:{step['platformJobId']}"
        try:
            pc_job = job_repository.get_by_platform_job_id("boss", pc_job_id, user_id=user_id)
        except KeyError as error:
            raise HTTPException(status_code=409, detail="职位快照未同步，不能分析") from error
        greeting = pc_job.generated_greeting
        if not greeting:
            default_greeting = str(profile.get("defaultGreeting") or "").strip()
            if run["configSnapshot"].get("greetingStrategy") == "custom":
                context = {
                    "job": pc_job.model_dump(mode="json", by_alias=True),
                    "profile": profile,
                    "localEvidence": [
                        item.model_dump(mode="json", by_alias=True) for item in match.evidence
                    ],
                    "defaultGreeting": default_greeting,
                    "match": {
                        "suitabilityScore": match.suitability_score,
                        "customizationConfidence": match.customization_confidence,
                        "materialStrategy": match.decision.material_strategy,
                    },
                }
                try:
                    generated = greeting_generator.generate(context, user_id=user_id)
                    greeting = str(generated["greeting"]).strip()
                except (RuntimeError, KeyError, TypeError):
                    greeting = default_greeting or (
                        f"您好，我对贵司的{pc_job.title}岗位很感兴趣，"
                        "希望有机会进一步沟通，谢谢。"
                    )
            if not greeting:
                greeting = str(run["configSnapshot"].get("fallbackGreeting") or "").strip()
            if not greeting:
                greeting = f"您好，我对贵司的{pc_job.title}岗位很感兴趣，希望进一步沟通，谢谢。"
            job_repository.update_generated_greeting(pc_job.id, greeting, user_id=user_id)
        try:
            saved = repository.save_analysis(
                user_id,
                run_id,
                step_id,
                score=match.suitability_score,
                confidence=match.customization_confidence,
                should_deliver=match.decision.should_deliver,
                reasons=match.decision.reasons,
                rules=[
                    item.model_dump(mode="json", by_alias=True)
                    for item in match.decision.rule_matches
                ],
                risks=[item.normalized_value for item in match.analysis.risk_requirements],
                greeting=greeting,
                resume_id=run["configSnapshot"].get("resumeId"),
            )
            saved["match"] = match.model_dump(mode="json", by_alias=True)
            return saved
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/agent/runs/{run_id}/jobs/{step_id}/result")
    def save_job_result(
        run_id: int, step_id: int, payload: JobResultInput, request: Request
    ) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        user_id = int(identity["user"]["id"])
        get_run_or_404(run_id, user_id)
        try:
            step = repository.save_result(
                user_id,
                run_id,
                step_id,
                payload.outcome,
                payload.idempotency_key,
                payload.evidence,
                payload.error_message,
            )
            snapshot = step.get("snapshot") or {}
            pc_job_id = f"codex-phone:{step['platformJobId']}"
            try:
                pc_job = job_repository.get_by_platform_job_id(
                    "boss", pc_job_id, user_id=user_id
                )
            except KeyError as error:
                raise HTTPException(
                    status_code=409, detail="职位快照未同步，不能记录结果"
                ) from error
            delivery_repository.upsert(
                DeliveryRecordInput(
                    platform="boss",
                    platform_job_id=pc_job_id,
                    title=pc_job.title,
                    company_name=pc_job.company_name,
                    salary_text=pc_job.salary_text,
                    location=pc_job.location,
                    recruiter_name=pc_job.recruiter_name,
                    status=payload.outcome,
                    decision="deliver" if step["shouldDeliver"] else "skip",
                    reason=payload.error_message or _optional_text(payload.evidence.get("reason")),
                    greeting_text=(
                        _optional_text(payload.evidence.get("sentText"))
                        if payload.outcome == "delivered"
                        else None
                    ) or step.get("greeting"),
                    detail=f"Codex 手机投递运行 #{run_id}，岗位步骤 #{step_id}",
                    applied_at=datetime.now(UTC),
                    metadata={
                        "source": "codex-phone",
                        "runId": run_id,
                        "stepId": step_id,
                        "snapshotId": snapshot.get("pcSnapshotId"),
                        "outcome": payload.outcome,
                        "evidence": payload.evidence,
                    },
                ),
                user_id=user_id,
            )
            if payload.outcome == "delivered":
                job_repository.update_tracking(
                    pc_job.id,
                    {
                        "has_communicated": True,
                        "has_interview": pc_job.has_interview,
                        "generated_greeting": step.get("greeting"),
                        "resume_variant": pc_job.resume_variant,
                        "generated_resume_id": pc_job.generated_resume_id,
                        "resume_optimization": pc_job.resume_optimization,
                    },
                    user_id=user_id,
                )
            return {"step": step, "run": repository.get_run(run_id, user_id=user_id)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="岗位步骤不存在") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/agent/runs/{run_id}/pause")
    def pause_run(run_id: int, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        try:
            return repository.pause_run(run_id, int(identity["user"]["id"]))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="任务不存在") from error

    @router.post("/agent/runs/{run_id}/finish")
    def finish_run(run_id: int, payload: RunFinishInput, request: Request) -> dict[str, Any]:
        identity = agent_identity(request, "agent:run")
        try:
            return repository.finish_run(
                run_id, int(identity["user"]["id"]), payload.status, payload.reason
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="任务不存在") from error

    return router


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,，|\n;/；]+", str(value or "")) if item.strip()]


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _matching_rules(repository: LibraryRepository, user_id: int) -> list[RiskRuleInput]:
    rules: list[RiskRuleInput] = []
    for record in repository.list("rules", user_id=user_id):
        data = record["data"]
        patterns = _string_list(data.get("patterns") or data.get("pattern"))
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
