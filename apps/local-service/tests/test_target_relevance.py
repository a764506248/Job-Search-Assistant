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
        ("后端开发工程师", "负责 Agent 工作流编排与工具调用接口开发"),
        ("AI 算法工程师", "负责工业智能体场景中的算法开发和优化"),
        ("AI Agent 工程师", "负责 RAG 检索增强系统开发与优化"),
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


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("AI Agent 工程师", "负责普通报表维护，了解 Agent 行业动态"),
        ("AI 全栈开发", "负责 AI 全栈系统开发与维护，结合 AI 能力提升智能化水平"),
        ("AI 算法工程师", "负责药物研发中的机器学习模型与数据挖掘"),
        ("遥感 AI 应用工程师", "负责遥感影像处理和目标检测模型部署"),
    ],
)
def test_ai_agent_target_does_not_match_title_or_generic_ai_work_alone(
    title: str, description: str,
) -> None:
    result = evaluate_target_relevance(
        title=title,
        description=description,
        target_roles=["AI Agent 开发工程师"],
        search_keywords=["AI Agent 开发工程师"],
    )

    assert result.relevant is False
    assert "JD" in (result.reason or "")


def test_other_targets_are_not_changed_by_ai_agent_gate() -> None:
    result = evaluate_target_relevance(
        title="机械工程师",
        description="负责机械结构设计",
        target_roles=["机械工程师"],
        search_keywords=["机械工程师"],
    )

    assert result.relevant is True


@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("AI全栈工程师（AI Native）", "使用 AI 编程工具进行产品快速原型开发与迭代，参与产品设计讨论"),
        ("高级 AI 产品经理（Agent 智能与评测）", "负责智能体产品规划、需求调研和产品落地"),
        ("AI 应用开发工程师", "负责 AI 产品开发与产品迭代"),
    ],
)
def test_explicit_ai_product_target_accepts_product_work(
    title: str, description: str,
) -> None:
    result = evaluate_target_relevance(
        title=title,
        description=description,
        target_roles=["AI Agent 开发工程师", "AI 产品"],
        search_keywords=[],
    )
    assert result.relevant is True


def test_ai_product_is_not_inferred_from_agent_target_alone() -> None:
    result = evaluate_target_relevance(
        title="AI全栈工程师（AI Native）",
        description="负责产品快速原型开发与迭代",
        target_roles=["AI Agent 开发工程师"],
        search_keywords=[],
    )
    assert result.relevant is False
