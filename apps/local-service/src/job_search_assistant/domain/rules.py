import re

from .models import RiskRuleInput, RuleMatch


def match_rules(job_text: str, rules: list[RiskRuleInput]) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for rule in rules:
        if not rule.enabled:
            continue

        evidence: list[str] = []
        for pattern in rule.patterns:
            match = re.search(re.escape(pattern), job_text, flags=re.IGNORECASE)
            if match:
                evidence.append(match.group(0))

        if evidence:
            matches.append(
                RuleMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    action=rule.action,
                    evidence=list(dict.fromkeys(evidence)),
                )
            )
    return matches
