import re
from collections.abc import Iterator
from dataclasses import dataclass

from .models import (
    JdAnalysisResponse,
    ParsedRequirement,
    RequirementCategory,
    RequirementLevel,
    TextEvidence,
)

PARSER_VERSION = "jd-rule-parser-1"

ELITE_SCHOOL_PATTERN = re.compile(r"985|211|双一流|名校|重点院校")
DEGREE_PATTERN = re.compile(r"博士|硕士|研究生|本科|大专|专科|高中")
NEGATION_PATTERN = re.compile(
    r"不限|不要求|不看|无.{0,4}要求|不强制|不卡|不作为.{0,6}要求|并非.{0,6}要求"
)
CONTEXT_PATTERN = re.compile(r"团队|成员|创始人|同事|管理层|核心人员")
CONTEXT_ORIGIN_PATTERN = re.compile(r"来自|毕业于|背景|出身|均为|都是")
REQUIRED_PATTERN = re.compile(r"仅限|必须|硬性|要求|只招|非.{0,12}勿投|第一学历")
PREFERRED_PATTERN = re.compile(r"优先|加分|更佳|倾向")


@dataclass(frozen=True)
class Sentence:
    text: str
    start: int
    end: int


def _sentences(text: str) -> Iterator[Sentence]:
    for match in re.finditer(r"[^。！？；;\n]+[。！？；;\n]?", text):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing_text = raw.rstrip()
        if not trailing_text.strip():
            continue
        start = match.start() + leading
        end = match.start() + len(trailing_text)
        yield Sentence(text=text[start:end], start=start, end=end)


def _level(sentence: str, *, elite_school: bool) -> RequirementLevel:
    if NEGATION_PATTERN.search(sentence):
        return RequirementLevel.NEGATED
    is_team_context = CONTEXT_PATTERN.search(sentence) and CONTEXT_ORIGIN_PATTERN.search(sentence)
    if elite_school and is_team_context:
        return RequirementLevel.CONTEXT
    if REQUIRED_PATTERN.search(sentence):
        return RequirementLevel.REQUIRED
    if PREFERRED_PATTERN.search(sentence):
        return RequirementLevel.PREFERRED
    return RequirementLevel.NEUTRAL


def _explanation(category: RequirementCategory, level: RequirementLevel) -> str:
    subject = "学校背景" if category == RequirementCategory.ELITE_SCHOOL else "学历"
    messages = {
        RequirementLevel.REQUIRED: f"文本将{subject}表述为明确要求",
        RequirementLevel.PREFERRED: f"文本将{subject}表述为优先条件",
        RequirementLevel.NEUTRAL: f"文本提到了{subject}，但没有明确要求强度",
        RequirementLevel.NEGATED: f"文本明确否定了对{subject}的限制",
        RequirementLevel.CONTEXT: "文本只是在描述团队或人员背景，不是招聘要求",
    }
    return messages[level]


def _requirement(
    sentence: Sentence,
    category: RequirementCategory,
    normalized_value: str,
    level: RequirementLevel,
) -> ParsedRequirement:
    return ParsedRequirement(
        category=category,
        level=level,
        normalized_value=normalized_value,
        evidence=TextEvidence(text=sentence.text, start=sentence.start, end=sentence.end),
        explanation=_explanation(category, level),
    )


def analyze_jd(job_text: str) -> JdAnalysisResponse:
    requirements: list[ParsedRequirement] = []
    for sentence in _sentences(job_text):
        elite_matches = list(ELITE_SCHOOL_PATTERN.finditer(sentence.text))
        if elite_matches:
            normalized = sorted({match.group(0) for match in elite_matches})
            level = _level(sentence.text, elite_school=True)
            requirements.append(
                _requirement(
                    sentence,
                    RequirementCategory.ELITE_SCHOOL,
                    "|".join(normalized),
                    level,
                )
            )

        degree_matches = list(DEGREE_PATTERN.finditer(sentence.text))
        if degree_matches:
            normalized = sorted({match.group(0) for match in degree_matches})
            level = _level(sentence.text, elite_school=False)
            requirements.append(
                _requirement(
                    sentence,
                    RequirementCategory.EDUCATION_DEGREE,
                    "|".join(normalized),
                    level,
                )
            )

    risk_requirements = [
        requirement
        for requirement in requirements
        if requirement.category == RequirementCategory.ELITE_SCHOOL
        and requirement.level in {RequirementLevel.REQUIRED, RequirementLevel.PREFERRED}
    ]
    return JdAnalysisResponse(
        requirements=requirements,
        risk_requirements=risk_requirements,
        has_risk_signals=bool(risk_requirements),
        parser_version=PARSER_VERSION,
    )
