import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import RiskRuleInput, RuleAction

PUA_DIGIT_START = 0xE031
PUA_DIGIT_END = 0xE03A

_MONTHLY_K_RANGE = re.compile(
    r"(?<!\d)(?P<minimum>\d+(?:\.\d+)?)\s*[kK]?\s*"
    r"(?:-|－|–|—|~|～|至)\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)\s*[kK](?![A-Za-z])"
)
_NON_MONTHLY_PAY = re.compile(
    r"(?:元|块)\s*(?:/|／|每)?\s*(?:天|日|时|小时)|(?:日薪|时薪|天薪|小时薪)"
)
_SALARY_RULE_NAME = re.compile(r"薪资|薪酬|工资|价格")
_ALLOWED_RANGE_INTENT = re.compile(
    r"(?:不在|未在|超出|超过).{0,20}(?:区间|范围).{0,20}(?:禁止|不投|拒绝|排除)"
    r"|(?:区间|范围).{0,12}(?:之外|以外|外).{0,20}(?:禁止|不投|拒绝|排除)"
)


@dataclass(frozen=True)
class MonthlySalaryRange:
    minimum_k: Decimal
    maximum_k: Decimal


@dataclass(frozen=True)
class SalaryRangeConstraint:
    rule_id: str
    rule_name: str
    pattern: str
    minimum_k: Decimal
    maximum_k: Decimal


@dataclass(frozen=True)
class SalaryPolicyViolation:
    rule_id: str
    rule_name: str
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class SalaryPolicyResult:
    normalized_text: str | None
    monthly_range: MonthlySalaryRange | None
    violations: tuple[SalaryPolicyViolation, ...]

    @property
    def allowed(self) -> bool:
        return not self.violations


def normalize_salary_text(value: str | None) -> str | None:
    """Decode BOSS private-use salary digits and return a stable display value."""
    if value is None:
        return None
    decoded = "".join(
        str(ord(character) - PUA_DIGIT_START)
        if PUA_DIGIT_START <= ord(character) <= PUA_DIGIT_END
        else character
        for character in value
    ).strip()
    return decoded or None


def contains_private_use(value: str | None) -> bool:
    return bool(value) and any(unicodedata.category(character) == "Co" for character in value)


def prefer_salary_text(existing: str | None, incoming: str | None) -> str | None:
    """Prefer decoded input, but never replace readable history with unresolved PUA text."""
    normalized_existing = normalize_salary_text(existing)
    normalized_incoming = normalize_salary_text(incoming)
    if normalized_incoming is None:
        return normalized_existing
    if (
        normalized_existing is not None
        and contains_private_use(normalized_incoming)
        and not contains_private_use(normalized_existing)
    ):
        return normalized_existing
    return normalized_incoming


def parse_monthly_salary_range(value: str | None) -> MonthlySalaryRange | None:
    normalized = normalize_salary_text(value)
    if (
        not normalized
        or contains_private_use(normalized)
        or _NON_MONTHLY_PAY.search(normalized)
    ):
        return None
    match = _MONTHLY_K_RANGE.search(normalized)
    if match is None:
        return None
    try:
        minimum = Decimal(match.group("minimum"))
        maximum = Decimal(match.group("maximum"))
    except InvalidOperation:
        return None
    if minimum <= 0 or maximum < minimum:
        return None
    return MonthlySalaryRange(minimum_k=minimum, maximum_k=maximum)


def salary_range_constraints(rules: list[RiskRuleInput]) -> list[SalaryRangeConstraint]:
    constraints: list[SalaryRangeConstraint] = []
    for rule in rules:
        if not rule.enabled or rule.action != RuleAction.BLOCK_DELIVERY:
            continue
        for pattern in rule.patterns:
            normalized_pattern = normalize_salary_text(pattern) or ""
            parsed = parse_monthly_salary_range(normalized_pattern)
            salary_named = bool(
                _SALARY_RULE_NAME.search(rule.name)
                or _SALARY_RULE_NAME.search(normalized_pattern)
            )
            if (
                parsed is None
                or not salary_named
                or _ALLOWED_RANGE_INTENT.search(normalized_pattern) is None
            ):
                continue
            constraints.append(
                SalaryRangeConstraint(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    pattern=normalized_pattern,
                    minimum_k=parsed.minimum_k,
                    maximum_k=parsed.maximum_k,
                )
            )
    return constraints


def evaluate_salary_policy(
    salary_text: str | None,
    *,
    minimum_salary_k: int,
    rules: list[RiskRuleInput],
) -> SalaryPolicyResult:
    normalized = normalize_salary_text(salary_text)
    monthly_range = parse_monthly_salary_range(normalized)
    constraints = salary_range_constraints(rules)
    requires_monthly_range = minimum_salary_k > 0 or bool(constraints)
    if not requires_monthly_range:
        return SalaryPolicyResult(normalized, monthly_range, ())

    if monthly_range is None:
        if normalized is None:
            detail = "岗位未提供薪资"
        elif contains_private_use(normalized):
            detail = f"岗位薪资“{normalized}”包含无法识别的私有区字符"
        elif _NON_MONTHLY_PAY.search(normalized):
            detail = f"岗位薪资“{normalized}”不是月薪 K 区间"
        else:
            detail = f"岗位薪资“{normalized}”无法解析为月薪 K 区间"
        if minimum_salary_k > 0:
            rule_id = "builtin:minimum-salary"
            rule_name = "最低薪资"
            suffix = f"，无法验证最低薪资 {minimum_salary_k}K，已禁止自动投递"
        else:
            constraint = constraints[0]
            rule_id = constraint.rule_id
            rule_name = constraint.rule_name
            suffix = "，无法验证允许薪资区间，已禁止自动投递"
        return SalaryPolicyResult(
            normalized,
            None,
            (
                SalaryPolicyViolation(
                    rule_id=rule_id,
                    rule_name=rule_name,
                    reason=detail + suffix,
                    evidence=(normalized or "未提供薪资",),
                ),
            ),
        )

    violations: list[SalaryPolicyViolation] = []
    # A salary preference is satisfied when the advertised interval has any
    # overlap with the requested floor. For example, 16-22K overlaps a 20K
    # minimum at 20-22K and must not be rejected solely because its lower
    # bound is below 20K.
    if minimum_salary_k > 0 and monthly_range.maximum_k < Decimal(minimum_salary_k):
        violations.append(
            SalaryPolicyViolation(
                rule_id="builtin:minimum-salary",
                rule_name="最低薪资",
                reason=(
                    f"岗位月薪上限 {_format_k(monthly_range.maximum_k)}K "
                    f"低于最低薪资 {minimum_salary_k}K，无交集"
                ),
                evidence=(normalized or "",),
            )
        )

    for constraint in constraints:
        if (
            monthly_range.maximum_k < constraint.minimum_k
            or monthly_range.minimum_k > constraint.maximum_k
        ):
            violations.append(
                SalaryPolicyViolation(
                    rule_id=constraint.rule_id,
                    rule_name=constraint.rule_name,
                    reason=(
                        "岗位月薪区间 "
                        f"{_format_k(monthly_range.minimum_k)}-"
                        f"{_format_k(monthly_range.maximum_k)}K 与规则允许的 "
                        f"{_format_k(constraint.minimum_k)}-"
                        f"{_format_k(constraint.maximum_k)}K 无交集"
                    ),
                    evidence=(normalized or "", constraint.pattern),
                )
            )
    return SalaryPolicyResult(normalized, monthly_range, tuple(violations))


def _format_k(value: Decimal) -> str:
    return format(value.normalize(), "f")
