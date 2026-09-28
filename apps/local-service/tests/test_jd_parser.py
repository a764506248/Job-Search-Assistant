import pytest

from job_search_assistant.domain.jd_parser import analyze_jd
from job_search_assistant.domain.models import RequirementLevel


@pytest.mark.parametrize(
    ("text", "expected_level", "expected_default"),
    [
        ("学历要求：仅限985、211院校本科毕业。", RequirementLevel.REQUIRED, True),
        ("985或211院校毕业者优先。", RequirementLevel.PREFERRED, True),
        ("我们不要求985、211背景，更看重项目能力。", RequirementLevel.NEGATED, False),
        ("团队核心成员均来自985、211高校。", RequirementLevel.CONTEXT, False),
        ("不卡第一学历，也不看是否双一流。", RequirementLevel.NEGATED, False),
    ],
)
def test_elite_school_context_is_classified(
    text: str,
    expected_level: RequirementLevel,
    expected_default: bool,
) -> None:
    result = analyze_jd(text)
    requirement = next(item for item in result.requirements if item.category == "elite_school")

    assert requirement.level == expected_level
    assert requirement.evidence.text == text
    assert text[requirement.evidence.start : requirement.evidence.end] == text
    assert result.has_risk_signals is expected_default


def test_degree_and_elite_school_are_separate_requirements() -> None:
    text = "本科及以上学历，985、211院校优先。"

    result = analyze_jd(text)

    assert {item.category for item in result.requirements} == {
        "education_degree",
        "elite_school",
    }
    assert result.has_risk_signals is True


def test_evidence_offsets_work_across_multiple_sentences() -> None:
    text = "负责RAG平台研发。\n团队成员来自985高校，不作为招聘要求。"

    result = analyze_jd(text)
    requirement = result.requirements[0]

    assert requirement.level == RequirementLevel.NEGATED
    assert text[requirement.evidence.start : requirement.evidence.end] == requirement.evidence.text
