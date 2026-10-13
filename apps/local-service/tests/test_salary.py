from decimal import Decimal

import pytest

from job_search_assistant.domain.models import RiskRuleInput, RuleAction
from job_search_assistant.domain.salary import (
    evaluate_salary_policy,
    normalize_salary_text,
    parse_monthly_salary_range,
    prefer_salary_text,
    salary_range_constraints,
)


def price_rule() -> RiskRuleInput:
    return RiskRuleInput(
        id="library:29",
        name="价格",
        patterns=["18k-35k不在这个价格区间的禁止投递"],
        action=RuleAction.BLOCK_DELIVERY,
    )


def test_normalizes_boss_private_use_salary_digits_and_parses_monthly_range() -> None:
    raw = "\ue033\ue031-\ue035\ue031K·\ue032\ue035薪"

    assert normalize_salary_text(raw) == "20-40K·14薪"
    parsed = parse_monthly_salary_range(raw)
    assert parsed is not None
    assert parsed.minimum_k == Decimal("20")
    assert parsed.maximum_k == Decimal("40")


@pytest.mark.parametrize(
    "salary",
    [
        None,
        "",
        "面议",
        "300-500元/天",
        "60-150元/时",
        "\ue100-\ue101K",
        "20-30K\ue100",
    ],
)
def test_minimum_salary_fails_closed_when_monthly_k_range_is_unverifiable(
    salary: str | None,
) -> None:
    result = evaluate_salary_policy(salary, minimum_salary_k=20, rules=[])

    assert result.allowed is False
    assert result.violations[0].rule_id == "builtin:minimum-salary"
    assert "禁止自动投递" in result.violations[0].reason


def test_minimum_salary_accepts_an_overlapping_advertised_range() -> None:
    result = evaluate_salary_policy("15-30K·14薪", minimum_salary_k=20, rules=[])

    assert result.allowed is True


def test_minimum_salary_rejects_a_disjoint_advertised_range() -> None:
    result = evaluate_salary_policy("15-19K·14薪", minimum_salary_k=20, rules=[])

    assert result.allowed is False
    assert "上限 19K 低于最低薪资 20K，无交集" in result.violations[0].reason


def test_extracts_allowed_range_from_blocking_price_rule() -> None:
    constraints = salary_range_constraints([price_rule()])

    assert len(constraints) == 1
    assert constraints[0].minimum_k == Decimal("18")
    assert constraints[0].maximum_k == Decimal("35")


def test_price_rule_accepts_overlapping_job_range_and_rejects_disjoint_range() -> None:
    overlapping = evaluate_salary_policy(
        "20-40K·14薪",
        minimum_salary_k=20,
        rules=[price_rule()],
    )
    wide_overlapping = evaluate_salary_policy(
        "30-60K·14薪",
        minimum_salary_k=20,
        rules=[price_rule()],
    )
    disjoint = evaluate_salary_policy(
        "36-60K·14薪",
        minimum_salary_k=20,
        rules=[price_rule()],
    )

    assert overlapping.allowed is True
    assert wide_overlapping.allowed is True
    assert disjoint.allowed is False
    assert disjoint.violations[0].rule_id == "library:29"
    assert "36-60K 与规则允许的 18-35K 无交集" in disjoint.violations[0].reason


def test_unresolved_private_use_text_never_overwrites_readable_history() -> None:
    assert prefer_salary_text("25-35K", "\ue100-\ue101K") == "25-35K"
