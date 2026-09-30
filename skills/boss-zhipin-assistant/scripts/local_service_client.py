#!/usr/bin/env python3
"""将投递结果写入 Job Search Assistant 本地服务。

服务暂时不可用时，记录进入工作目录中的 delivery_outbox.json；下一次写入前会自动重试。
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.profile_loader import GREETING_TEXT, LOCAL_SERVICE_URL, WORK_DIR

DELIVERIES_URL = f"{LOCAL_SERVICE_URL}/v1/deliveries"
DEFAULT_RESUME_IMAGE_URL = f"{LOCAL_SERVICE_URL}/v1/resumes/default-image"
OUTBOX_FILE = os.path.join(WORK_DIR, "delivery_outbox.json")


def _json_request(path, method="GET", payload=None, timeout=30):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{LOCAL_SERVICE_URL}{path}", data=body, headers=headers, method=method
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"本地服务 HTTP {error.code}: {detail[:500]}") from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"本地服务请求失败: {error}") from error


def get_automation_config():
    """读取本地数据库中的目标、阈值、匹配规则和默认材料配置。"""
    return _json_request("/v1/automation/config")


def analyze_and_plan_job(current_jd):
    """原子执行职位快照落库、RAG 匹配、规则判断和问候语生成。"""
    jd = current_jd.get("jd_full", {}) or {}
    surface = current_jd.get("surface_info", {}) or {}
    job_id = str(current_jd.get("jobId") or surface.get("jobId") or "").strip()
    if not job_id:
        raise RuntimeError("当前职位缺少 jobId")
    title = str(jd.get("job_title") or current_jd.get("title") or surface.get("title") or "").strip()
    company = str(jd.get("company") or current_jd.get("company") or surface.get("company") or "").strip()
    description = str(jd.get("jd_text") or current_jd.get("jd_text") or jd.get("full_text") or "").strip()
    if not title or not company or not description:
        raise RuntimeError("当前职位缺少 title、companyName 或 description，不能生成投递计划")
    return _json_request(
        "/v1/jobs/analyze-and-plan",
        method="POST",
        timeout=90,
        payload={
            "job": {
                "platform": "boss",
                "platformJobId": job_id,
                "url": str(surface.get("url") or f"https://www.zhipin.com/job_detail/{job_id}.html"),
                "title": title,
                "companyName": company,
                "companySize": jd.get("company_size") or surface.get("company_size"),
                "location": jd.get("city") or surface.get("location"),
                "workAddress": jd.get("work_address") or surface.get("work_address"),
                "salaryText": jd.get("salary_decrypted") or jd.get("salary") or current_jd.get("salary"),
                "experience": jd.get("experience"),
                "education": jd.get("degree"),
                "description": description,
                "skills": surface.get("skills", []),
                "recruiterName": jd.get("boss_name"),
                "recruiterTitle": jd.get("boss_title"),
                "capturedAt": datetime.now(UTC).isoformat(),
                "source": "dom",
            }
        },
    )


def download_default_resume_image():
    """下载用户已选中的默认简历图片；临时文件由调用方删除。"""
    request = Request(DEFAULT_RESUME_IMAGE_URL, method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            content = response.read()
    except HTTPError as error:
        if error.code == 404:
            return None, "尚未配置默认简历图片"
        detail = error.read().decode("utf-8", errors="replace")
        return None, f"默认简历图片请求失败: HTTP {error.code} {detail[:200]}"
    except (URLError, TimeoutError, OSError) as error:
        return None, f"默认简历图片请求失败: {error}"

    if "image/png" not in content_type or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, f"默认简历图片格式异常: {content_type or 'unknown'}"

    fd, path = tempfile.mkstemp(prefix="boss-resume-", suffix=".png")
    with os.fdopen(fd, "wb") as file:
        file.write(content)
    return path, "默认简历图片已下载"


def _post(payload):
    request = Request(
        DELIVERIES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        return True, f"已写入数据库，记录 ID: {body.get('id', '-')}"
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return False, f"HTTP {error.code}: {detail[:300]}"
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        return False, str(error)


def _read_outbox():
    if not os.path.exists(OUTBOX_FILE):
        return []
    try:
        with open(OUTBOX_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_outbox(items):
    with open(OUTBOX_FILE, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def flush_outbox():
    """重试历史待同步记录，返回仍未同步的条数。"""
    pending = _read_outbox()
    remaining = []
    for payload in pending:
        ok, _ = _post(payload)
        if not ok:
            remaining.append(payload)
    _write_outbox(remaining)
    return len(remaining)


def _database_status(status, detail):
    if status == "success":
        return "greeting_sent" if GREETING_TEXT else "delivered"
    if status in {"skipped", "blocked", "fatal_limit"}:
        return status
    if "上限" in (detail or ""):
        return "fatal_limit"
    return "failed"


def save_delivery(
    job_info, status, detail="", decision="", reason="", metadata=None, greeting_text=None
):
    """保存一条投递结果；失败时排队，且不改变浏览器投递结果。"""
    flush_outbox()
    payload = {
        "platform": "boss",
        "platformJobId": str(job_info.get("jobId", "")),
        "title": job_info.get("title", "") or "未知岗位",
        "companyName": job_info.get("company", "") or "未知公司",
        "salaryText": job_info.get("salary", ""),
        "location": job_info.get("location", ""),
        "recruiterName": job_info.get("recruiter_name", ""),
        "status": _database_status(status, detail),
        "decision": decision or None,
        "reason": reason or None,
        "greetingText": (greeting_text or GREETING_TEXT) if status == "success" else None,
        "detail": detail or None,
        "appliedAt": datetime.now(UTC).isoformat(),
        "metadata": metadata or {},
    }
    if not payload["platformJobId"]:
        return False, "缺少 platformJobId，未写入数据库"

    ok, message = _post(payload)
    if ok:
        return True, message

    pending = _read_outbox()
    # 同一岗位只保留最新结果，防止本地队列重复增长。
    pending = [
        item for item in pending
        if not (
            item.get("platform") == payload["platform"]
            and item.get("platformJobId") == payload["platformJobId"]
        )
    ]
    pending.append(payload)
    _write_outbox(pending)
    return False, f"本地服务写入失败，已加入待同步队列: {message}"
