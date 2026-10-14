import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetRelevance:
    relevant: bool
    reason: str | None = None


_AI_AGENT_TARGET_MARKERS = ("aiagent", "agent", "智能体")
_AI_PRODUCT_TARGET_MARKERS = ("ai产品", "人工智能产品", "ainative")
_AI_PRODUCT_TITLE_MARKERS = (
    "ai产品", "人工智能产品", "ainative", "ai全栈", "ai应用",
)
_PRODUCT_WORK_MARKERS = (
    "产品开发", "产品设计", "原型开发", "产品迭代", "产品规划",
    "需求调研", "产品方案", "产品落地", "产品快速原型",
    "产品化", "产品功能", "ai解决方案", "方案落地", "版本迭代",
)
_AI_AGENT_TITLE_MARKERS = ("aiagent", "agent", "智能体")
_AGENT_DESCRIPTION_MARKERS = ("agent", "智能体")
_AGENT_WORK_MARKERS = (
    "开发", "研发", "设计", "构建", "实现", "搭建", "编排", "优化", "维护", "评测",
)
_RELATED_WORK_MARKERS = (
    "rag", "检索增强", "知识库", "大模型应用", "llm应用", "prompt工程",
    "提示词工程", "工具调用", "工作流编排",
)
_TECHNICAL_TITLE_MARKERS = (
    "开发",
    "工程师",
    "算法",
    "研发",
    "架构",
    "全栈",
    "后端",
    "前端",
    "技术",
)
_NON_TARGET_TITLE_MARKERS = (
    "机械",
    "硬件",
    "fpga",
    "嵌入式",
    "电气",
    "仿真",
    "芯片",
    "射频",
    "结构工程",
    "销售",
    "商务",
    "运营",
    "客服",
    "会计",
    "行政",
    "人事",
)


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-/（）()·]+", "", value.casefold())


def _has_agent_work(description: str) -> bool:
    # 同一句职责中必须同时出现 Agent 和实施动作；仅在福利/背景中提及不算。
    for sentence in re.split(r"[。；;\n]+", description.casefold()):
        normalized = _normalize(sentence)
        normalized = re.sub(
            r"(?:了解|关注|熟悉|接触|优先).{0,6}(?:agent|智能体)",
            "",
            normalized,
        )
        if any(marker in normalized for marker in _AGENT_DESCRIPTION_MARKERS) and any(
            marker in normalized for marker in _AGENT_WORK_MARKERS
        ):
            return True
    return False


def _has_related_work(description: str) -> bool:
    for sentence in re.split(r"[。；;\n]+", description.casefold()):
        normalized = _normalize(sentence)
        if any(marker in normalized for marker in _RELATED_WORK_MARKERS) and any(
            marker in normalized for marker in _AGENT_WORK_MARKERS
        ):
            return True
    return False


def evaluate_target_relevance(
    *,
    title: str,
    description: str,
    target_roles: list[str],
    search_keywords: list[str],
) -> TargetRelevance:
    """Apply a deterministic role-family gate before delivery decisions."""

    configured_targets = [
        _normalize(value)
        for value in [*target_roles, *search_keywords]
        if value and value.strip()
    ]
    wants_agent = any(
        marker in target
        for target in configured_targets
        for marker in _AI_AGENT_TARGET_MARKERS
    )
    wants_ai_product = any(
        marker in target
        for target in configured_targets
        for marker in _AI_PRODUCT_TARGET_MARKERS
    )
    if not wants_agent and not wants_ai_product:
        return TargetRelevance(relevant=True)

    normalized_title = _normalize(title)
    has_agent_title = any(
        marker in normalized_title for marker in _AI_AGENT_TITLE_MARKERS
    )
    has_technical_title = any(
        marker in normalized_title for marker in _TECHNICAL_TITLE_MARKERS
    )

    if any(marker in normalized_title for marker in _NON_TARGET_TITLE_MARKERS):
        return TargetRelevance(
            relevant=False,
            reason=(
                f"岗位“{title}”属于非 AI Agent 目标职类"
                if wants_agent and not wants_ai_product
                else f"岗位“{title}”属于非目标职类"
            ),
        )

    if (
        wants_ai_product
        and any(marker in normalized_title for marker in _AI_PRODUCT_TITLE_MARKERS)
        and any(marker in _normalize(description) for marker in _PRODUCT_WORK_MARKERS)
    ):
        return TargetRelevance(relevant=True)

    if wants_agent and has_technical_title and _has_agent_work(description):
        return TargetRelevance(relevant=True)

    # Agent 标题仍需 JD 提供技术工作依据，不能仅凭标题放行。
    if wants_agent and has_agent_title and has_technical_title and _has_related_work(description):
        return TargetRelevance(relevant=True)

    return TargetRelevance(
        relevant=False,
        reason=(
            f"岗位“{title}”与目标方向不相关；"
            "已结合岗位名称和 JD 判断：未找到足够的智能体开发或 AI 产品工作依据"
        ),
    )
