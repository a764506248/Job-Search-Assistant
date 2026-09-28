from .decision import evaluate_material_strategy
from .jd_parser import analyze_jd
from .models import (
    AutomaticJobMatchRequest,
    AutomaticJobMatchResponse,
    DecisionRequest,
    RagSearchResult,
    RiskRuleInput,
)


def build_automatic_match(
    request: AutomaticJobMatchRequest, evidence: list[dict[str, object]]
) -> AutomaticJobMatchResponse:
    analysis = analyze_jd(request.job_text)
    ranked = [RagSearchResult.model_validate(item) for item in evidence]
    scores = [max(0.0, min(1.0, item.score)) for item in ranked[:5]]
    best = scores[0] if scores else 0.0
    average = sum(scores) / len(scores) if scores else 0.0
    suitability = round(min(100.0, (best * 0.65 + average * 0.35) * 100))

    source_count = len({(item.source_type, item.source_id) for item in ranked})
    strong_evidence = sum(score >= 0.55 for score in scores)
    confidence = round(
        min(100.0, average * 65 + min(source_count, 3) * 7 + min(strong_evidence, 3) * 5)
    )

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
            suitability_score=suitability,
            customization_confidence=confidence,
            minimum_suitability_score=request.minimum_suitability_score,
            minimum_customization_confidence=request.minimum_customization_confidence,
            rules=rules,
            duplicate=request.duplicate,
            company_blocked=request.company_blocked,
        )
    )
    return AutomaticJobMatchResponse(
        analysis=analysis,
        suitability_score=suitability,
        customization_confidence=confidence,
        decision=decision,
        evidence=ranked,
    )
