from job_search_assistant.domain import DecisionRequest, build_automatic_match, evaluate_material_strategy
from job_search_assistant.domain.models import AutomaticJobMatchRequest, MaterialStrategy, RiskRuleInput, RuleAction


def test_high_match_uses_custom_materials() -> None:
    result = evaluate_material_strategy(
        DecisionRequest(
            job_text="负责 RAG 应用研发",
            suitability_score=88,
            customization_confidence=90,
        )
    )

    assert result.should_deliver is True
    assert result.material_strategy == MaterialStrategy.CUSTOM


def test_low_match_falls_back_and_still_delivers() -> None:
    result = evaluate_material_strategy(
        DecisionRequest(
            job_text="负责销售团队管理",
            suitability_score=30,
            customization_confidence=20,
        )
    )

    assert result.should_deliver is True
    assert result.material_strategy == MaterialStrategy.DEFAULT
    assert result.reasons == ["岗位适合度未达阈值，定制可信度未达阈值，改用默认材料"]


def test_risk_rule_uses_default_materials_and_still_delivers() -> None:
    result = evaluate_material_strategy(
        DecisionRequest(
            job_text="计算机相关专业，985、211 院校优先",
            suitability_score=90,
            customization_confidence=90,
            rules=[
                RiskRuleInput(
                    id="elite-school",
                    name="名校学历偏好",
                    patterns=["985", "211"],
                    action=RuleAction.USE_DEFAULT_MATERIALS,
                )
            ],
        )
    )

    assert result.should_deliver is True
    assert result.material_strategy == MaterialStrategy.DEFAULT
    assert result.rule_matches[0].evidence == ["985", "211"]


def test_company_blacklist_blocks_delivery() -> None:
    result = evaluate_material_strategy(
        DecisionRequest(
            job_text="任意职位",
            suitability_score=100,
            customization_confidence=100,
            company_blocked=True,
        )
    )

    assert result.should_deliver is False
    assert result.material_strategy == MaterialStrategy.BLOCKED


def test_score_penalty_can_trigger_default_materials() -> None:
    result = evaluate_material_strategy(
        DecisionRequest(
            job_text="该岗位需要驻场工作",
            suitability_score=80,
            customization_confidence=90,
            rules=[
                RiskRuleInput(
                    id="onsite",
                    name="驻场",
                    patterns=["驻场"],
                    action=RuleAction.REDUCE_SCORE,
                    score_penalty=10,
                )
            ],
        )
    )

    assert result.should_deliver is True
    assert result.effective_suitability_score == 70
    assert result.material_strategy == MaterialStrategy.DEFAULT


def test_custom_rule_can_match_job_title_and_block_rule_still_wins() -> None:
    result = build_automatic_match(
        AutomaticJobMatchRequest(
            title="AI Native 全栈工程师（外包）",
            job_text="负责产品开发与迭代",
            rules=[
                RiskRuleInput(
                    id="ai-product", name="AI 产品", patterns=["AI Native"],
                    action=RuleAction.USE_DEFAULT_MATERIALS,
                ),
                RiskRuleInput(
                    id="outsourcing", name="外包", patterns=["外包"],
                    action=RuleAction.BLOCK_DELIVERY,
                ),
            ],
        ),
        [],
    )

    assert {match.rule_id for match in result.decision.rule_matches} == {
        "ai-product", "outsourcing",
    }
    assert result.decision.should_deliver is False
