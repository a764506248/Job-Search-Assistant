import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetRelevance:
    relevant: bool
    reason: str | None = None


_AI_AGENT_TARGET_MARKERS = ("aiagent", "agent", "智能体")
_AI_AGENT_TITLE_MARKERS = ("aiagent", "agent", "智能体")
_AI_BROAD_TITLE_MARKERS = ("ai", "人工智能", "大模型", "llm", "rag", "算法")
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
    if not any(
        marker in target
        for target in configured_targets
        for marker in _AI_AGENT_TARGET_MARKERS
    ):
        return TargetRelevance(relevant=True)

    normalized_title = _normalize(title)
    normalized_description = _normalize(description)
    has_agent_title = any(
        marker in normalized_title for marker in _AI_AGENT_TITLE_MARKERS
    )
    has_technical_title = any(
        marker in normalized_title for marker in _TECHNICAL_TITLE_MARKERS
    )

    if any(marker in normalized_title for marker in _NON_TARGET_TITLE_MARKERS):
        return TargetRelevance(
            relevant=False,
            reason=f"岗位“{title}”属于非 AI Agent 目标职类",
        )

    if has_agent_title and has_technical_title:
        return TargetRelevance(relevant=True)

    # 部分企业使用“大模型应用/算法工程师”作标题，仅在 JD 中写明 Agent 职责。
    # 两类信号必须同时存在，避免普通后端岗位因 JD 偶然出现 Agent 而被放行。
    has_broad_ai_title = any(
        marker in normalized_title for marker in _AI_BROAD_TITLE_MARKERS
    )
    has_agent_description = any(
        marker in normalized_description for marker in _AI_AGENT_TITLE_MARKERS
    )
    if has_broad_ai_title and has_technical_title and has_agent_description:
        return TargetRelevance(relevant=True)

    return TargetRelevance(
        relevant=False,
        reason=(
            f"岗位“{title}”与目标“AI Agent”不相关；"
            "标题需明确包含 Agent/智能体，或为 AI/大模型技术岗且 JD 明确包含 Agent 职责"
        ),
    )
