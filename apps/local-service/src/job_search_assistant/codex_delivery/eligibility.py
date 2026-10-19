from __future__ import annotations

import re
from typing import Any

_DEGREE_RANK = {
    "初中": 1,
    "高中": 2,
    "中专": 2,
    "大专": 3,
    "专科": 3,
    "本科": 4,
    "硕士": 5,
    "研究生": 5,
    "博士": 6,
}
_DEGREE_PATTERN = re.compile("博士|硕士|研究生|本科|大专|专科|高中|中专|初中")
_HARD_REQUIREMENT_PATTERN = re.compile(
    "(博士|硕士|研究生|本科|大专|专科)(?:及以上|以上)?学历"
    "|(博士|硕士|研究生|本科|大专|专科)(?:及以上|以上)"
)


def _degree_rank(value: object) -> int | None:
    ranks = [_DEGREE_RANK[item] for item in _DEGREE_PATTERN.findall(str(value or ""))]
    return max(ranks, default=None)


def _required_degree(snapshot: dict[str, Any]) -> int | None:
    structured = str(snapshot.get("education") or "").strip()
    if structured and "不限" not in structured and "优先" not in structured:
        rank = _degree_rank(structured)
        if rank is not None:
            return rank

    description = str(snapshot.get("description") or "")
    hard_ranks: list[int] = []
    for match in _HARD_REQUIREMENT_PATTERN.finditer(description):
        # A nearby preference is not a mandatory degree requirement.
        if "优先" in description[match.end() : match.end() + 4]:
            continue
        rank = _degree_rank(match.group())
        if rank is not None:
            hard_ranks.append(rank)
    return max(hard_ranks, default=None)


def _profile_degree_rank(profile: dict[str, Any]) -> int | None:
    entries = profile.get("educations") or []
    values = [item.get("degree") for item in entries if isinstance(item, dict)]
    values.extend(item.get("content") for item in entries if isinstance(item, dict))
    values.append(profile.get("education"))
    return max(
        (rank for value in values if (rank := _degree_rank(value)) is not None),
        default=None,
    )


def _resume_degree_rank(resume: dict[str, Any]) -> int | None:
    data = resume.get("data") or {}
    if data.get("confirmationStatus") == "pending":
        return None
    structured = _profile_degree_rank(data)
    if structured is not None:
        return structured

    # Only inspect education sections, not project/JD text mentioning other degrees.
    raw_text = str(data.get("rawText") or "").replace("\r\n", "\n")
    sections = re.split(
        r"(?im)^[ \t]*(教育经历|教育背景|教育信息|education(?:[ \t]+background)?)"
        r"[ \t]*[：:]?[ \t]*$",
        raw_text,
    )
    ranks = []
    for section in sections[2::2]:
        education = re.split(
            r"(?im)^[ \t]*(?:工作经历|工作经验|项目经历|项目经验|项目实践|个人优势|"
            r"专业技能|技术栈|技能清单|自我评价|求职意向|work experience|"
            r"professional experience|projects|skills|summary)[ \t]*[：:]?[ \t]*$",
            section,
            maxsplit=1,
        )[0]
        if (rank := _degree_rank(education)) is not None:
            ranks.append(rank)
    return max(ranks, default=None)


def education_block_reason(
    snapshot: dict[str, Any],
    profile: dict[str, Any],
    selected_resume: dict[str, Any] | None = None,
) -> str | None:
    required = _required_degree(snapshot)
    if required is None:
        return None

    actual = _profile_degree_rank(profile)
    source = "个人档案"
    if actual is None and selected_resume is not None:
        actual = _resume_degree_rank(selected_resume)
        source = "所选简历"
    if actual is not None and actual >= required:
        return None

    required_label = next(label for label, rank in _DEGREE_RANK.items() if rank == required)
    if actual is None:
        # Missing evidence is not evidence of a mismatch. Keep the uncertainty
        # visible to the caller, but only block a known degree below the bar.
        return None
    actual_label = next(label for label, rank in _DEGREE_RANK.items() if rank == actual)
    return f"岗位要求{required_label}及以上学历，{source}为{actual_label}"


def education_uncertain_reason(
    snapshot: dict[str, Any],
    profile: dict[str, Any],
    selected_resume: dict[str, Any] | None = None,
) -> str | None:
    required = _required_degree(snapshot)
    if required is None or _profile_degree_rank(profile) is not None:
        return None
    if selected_resume is not None and _resume_degree_rank(selected_resume) is not None:
        return None
    required_label = next(label for label, rank in _DEGREE_RANK.items() if rank == required)
    sources = "个人档案和所选简历均" if selected_resume is not None else "个人档案"
    return (
        f"岗位要求{required_label}及以上学历，但{sources}未填写可核验学历；"
        "请核实，未作为自动拒投条件"
    )


def incomplete_title_reason(snapshot: dict[str, Any]) -> str | None:
    title = str(snapshot.get("title") or "").strip()
    if title.endswith(("…", "...", "（", "(")):
        return "岗位标题不完整，不能确认问候语与当前岗位一致"
    if title.count("（") > title.count("）") or title.count("(") > title.count(")"):
        return "岗位标题括号未闭合，可能是屏幕截断，不能自动发送"
    return None


def missing_linux_evidence_reason(snapshot: dict[str, Any], materials: list[object]) -> str | None:
    description = str(snapshot.get("description") or "")
    required = False
    for sentence in re.split(r"[。；;\n]", description):
        if (
            re.search(r"Linux.{0,8}(?:经验|能力)", sentence, re.IGNORECASE)
            and "优先" not in sentence
        ):
            required = True
            break
    if not required:
        return None
    if re.search(r"Linux", str(materials), re.IGNORECASE):
        return None
    return "岗位明确要求 Linux 经验，但个人档案、项目和简历中无可核验的相关证据"
