import re


def normalize_recruiter_activity(text: str | None) -> str:
    value = re.sub(r"\s+", "", text or "")
    if not value:
        return "unknown"
    if "刚刚活跃" in value or "刚刚在线" in value:
        return "just_now"
    if "在线" in value:
        return "online"
    if "今日活跃" in value or "今天活跃" in value:
        return "today"
    if re.search(r"(?:3|三)(?:日|天)内活跃|近(?:3|三)天活跃", value):
        return "within_3_days"
    if "本周活跃" in value:
        return "this_week"
    if "本月活跃" in value:
        return "this_month"
    if "活跃" in value and re.search(r"周|月|年|天前|日前", value):
        return "older"
    return "unknown"
