import pytest

from job_search_assistant.domain.target_relevance import evaluate_target_relevance


@pytest.mark.parametrize(
    "title",
    [
        "机械工程师",
        "仿真工程师261009",
        "FPGA开发工程师",
        "销售工程师",
        "Salesforce开发工程师",
        "数据开发工程师（可远程）",
        "后端开发工程师",
        "资深 Django 后端工程师",
    ],
)
def test_ai_agent_target_rejects_unrelated_titles(title: str) -> None:
    result = evaluate_target_relevance(
        title=title,
        description="负责系统开发，熟悉 Python 与数据处理",
        target_roles=["AI Agent 开发工程师"],
        search_keywords=["AI Agent 开发工程师"],
    )

    assert result.relevant is False
    assert result.reason


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("AI Agent 开发工程师", "负责智能体平台研发"),
        ("智能体应用研发工程师", "负责企业智能体应用开发"),
        ("大模型应用开发工程师", "负责 RAG 与 Agent 应用开发"),
        ("LLM 算法工程师", "负责多 Agent 协作与评测"),
    ],
)
def test_ai_agent_target_accepts_explicit_agent_roles(
    title: str, description: str
) -> None:
    result = evaluate_target_relevance(
        title=title,
        description=description,
        target_roles=["AI Agent 开发工程师"],
        search_keywords=["AI Agent 开发工程师"],
    )

    assert result.relevant is True


def test_other_targets_are_not_changed_by_ai_agent_gate() -> None:
    result = evaluate_target_relevance(
        title="机械工程师",
        description="负责机械结构设计",
        target_roles=["机械工程师"],
        search_keywords=["机械工程师"],
    )

    assert result.relevant is True
