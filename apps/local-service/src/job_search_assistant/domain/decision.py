from .models import DecisionRequest, DecisionResponse, MaterialStrategy, RuleAction
from .rules import match_rules


def evaluate_material_strategy(request: DecisionRequest) -> DecisionResponse:
    if request.company_blocked:
        return DecisionResponse(
            material_strategy=MaterialStrategy.BLOCKED,
            should_deliver=False,
            effective_suitability_score=request.suitability_score,
            reasons=["公司位于用户黑名单"],
            rule_matches=[],
        )

    if request.duplicate:
        return DecisionResponse(
            material_strategy=MaterialStrategy.BLOCKED,
            should_deliver=False,
            effective_suitability_score=request.suitability_score,
            reasons=["职位已经投递过"],
            rule_matches=[],
        )

    matches = match_rules(request.job_text, request.rules)
    penalties = {
        rule.id: rule.score_penalty
        for rule in request.rules
        if rule.enabled and rule.action == RuleAction.REDUCE_SCORE
    }
    effective_score = max(
        0,
        request.suitability_score - sum(penalties.get(match.rule_id, 0) for match in matches),
    )

    if any(match.action == RuleAction.BLOCK_DELIVERY for match in matches):
        return DecisionResponse(
            material_strategy=MaterialStrategy.BLOCKED,
            should_deliver=False,
            effective_suitability_score=effective_score,
            reasons=["命中禁止投递规则"],
            rule_matches=matches,
        )

    force_default = any(match.action == RuleAction.USE_DEFAULT_MATERIALS for match in matches)
    meets_threshold = (
        effective_score >= request.minimum_suitability_score
        and request.customization_confidence >= request.minimum_customization_confidence
    )

    if force_default:
        reasons = ["命中风险规则，使用默认简历和默认问候语"]
        strategy = MaterialStrategy.DEFAULT
    elif not meets_threshold:
        reasons = ["岗位适合度或定制可信度未达到阈值"]
        strategy = MaterialStrategy.DEFAULT
    else:
        reasons = ["岗位适合度和定制可信度均达到阈值"]
        strategy = MaterialStrategy.CUSTOM

    return DecisionResponse(
        material_strategy=strategy,
        should_deliver=True,
        effective_suitability_score=effective_score,
        reasons=reasons,
        rule_matches=matches,
    )
