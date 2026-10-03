from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .repositories import LibraryRepository


class ProjectExtractor(Protocol):
    def extract(
        self, resume_text: str, model_record_id: int | None = None
    ) -> list[dict[str, object]]: ...

    def extract_resume(
        self, resume_text: str, model_record_id: int | None = None
    ) -> dict[str, object]: ...


class ModelConnectionTester(Protocol):
    def test(self, config: dict[str, object]) -> dict[str, object]: ...


class MaterialPreviewGenerator(Protocol):
    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]: ...


class GreetingGenerator(Protocol):
    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]: ...


class JobAnalysisGenerator(Protocol):
    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]: ...


class CloudModelConnectionTester:
    """发送最小请求，验证模型地址、Key 和模型 ID 是否可用。"""

    def test(self, config: dict[str, object]) -> dict[str, object]:
        model_id, api_key, base_url, provider = _model_settings(config)
        started = perf_counter()
        prompt = "这是连接测试。请只回复 OK。"
        if provider == "Anthropic":
            reply = CloudProjectExtractor._call_anthropic(
                base_url, api_key, model_id, prompt, max_tokens=16
            )
        else:
            reply = CloudProjectExtractor._call_openai_compatible(
                base_url, api_key, model_id, prompt
            )
        if not reply.strip():
            raise RuntimeError("模型接口返回了空内容")
        return {
            "ok": True,
            "provider": provider,
            "modelId": model_id,
            "latencyMs": round((perf_counter() - started) * 1000),
            "message": "连接成功，模型已返回内容",
        }


def _model_settings(config: dict[str, object]) -> tuple[str, str, str, str]:
    model_id = str(config.get("modelId", "")).strip()
    api_key = str(config.get("apiKey", "")).strip()
    base_url = str(config.get("baseUrl", "")).strip().rstrip("/")
    provider = str(config.get("provider", "OpenAI Compatible"))
    if not model_id or not api_key or not base_url:
        raise RuntimeError("模型配置不完整，需要模型 ID、API Key 和 Base URL")
    return model_id, api_key, base_url, provider


def _model_candidates(
    library: LibraryRepository, model_record_id: int | None = None
) -> list[dict[str, object]]:
    """Return primary then fallback model, without retrying the same record."""
    configs = library.list("models")
    if not configs:
        raise RuntimeError("尚未配置云端模型，请先填写模型 ID、API Key 和 Base URL")
    selected: dict[str, object] | None = None
    if model_record_id is not None:
        selected = next((item for item in configs if item["id"] == model_record_id), None)
        if selected is None:
            raise RuntimeError("选择的模型配置不存在或已被删除")
    else:
        selected = next(
            (item for item in configs if item["data"].get("usageRole") == "primary"),
            configs[0],
        )
    fallback = next(
        (
            item
            for item in configs
            if item["id"] != selected["id"]
            and item["data"].get("usageRole") == "fallback"
        ),
        None,
    )
    if fallback is None:
        fallback = next((item for item in configs if item["id"] != selected["id"]), None)
    return [selected, *([fallback] if fallback else [])]


class CloudProjectExtractor:
    """使用主模型和兜底模型提取完整的结构化简历。"""

    def __init__(self, library: LibraryRepository) -> None:
        self.library = library

    def extract(
        self, resume_text: str, model_record_id: int | None = None
    ) -> list[dict[str, object]]:
        return list(self.extract_resume(resume_text, model_record_id)["projects"])

    def extract_resume(
        self, resume_text: str, model_record_id: int | None = None
    ) -> dict[str, object]:
        prompt = self._prompt(resume_text[:60000])
        errors: list[str] = []
        for record in _model_candidates(self.library, model_record_id):
            config = record["data"]
            try:
                model_id, api_key, base_url, provider = _model_settings(config)
                if provider == "Anthropic":
                    content = self._call_anthropic(base_url, api_key, model_id, prompt)
                else:
                    content = self._call_openai_compatible(
                        base_url, api_key, model_id, prompt
                    )
                parsed = self._parse_resume(content)
                return {
                    **parsed,
                    "modelRecordId": record["id"],
                    "modelName": record["name"],
                    "modelId": model_id,
                    "attemptErrors": errors,
                }
            except RuntimeError as error:
                errors.append(f"{record['name']}：{error}")
        raise RuntimeError("；".join(errors))

    @staticmethod
    def _prompt(resume_text: str) -> str:
        return f"""你是严格的中文简历结构化提取器。请完整读取原文，一次性提取个人档案、
个人优势、技术栈、工作经历、教育经历和所有真实项目。
严禁补充原文不存在的事实、数字、公司、学校、职责或技术。

提取规则：
1. 一个有独立名称、背景/目标、职责或成果的项目对应 projects 中一个对象；不同项目不得合并。
2. 架构图中的模块名、技术名、章节标题和单条个人优势不是独立项目；
   同一项目的多条职责与成果必须保留在同一个项目对象中。
3. strengths 只放个人优势，不得把项目、工作经历、技术栈或章节标题逐行塞入。
4. 工作经历与教育经历逐段保留；无法确定的字段返回空字符串或空数组，不猜测。
5. evidence 必须是能支持该实体的原文摘录，便于人工核验。
6. 只返回合法 JSON，不要 Markdown、解释或代码围栏。JSON 格式必须为：
{{
  "profile": {{
    "displayName":"姓名或空字符串", "targetRoles":"目标岗位或空字符串",
    "yearsExperience":"工作年限或空字符串", "cities":"期望城市或空字符串",
    "phone":"电话或空字符串", "email":"邮箱或空字符串",
    "strengths":[{{"content":"完整优势条目","evidence":"原文摘录"}}],
    "techStackGroups":[{{"name":"技术类别","items":["技术"]}}],
    "workExperiences":[{{"company":"公司","role":"职位","startDate":"原文日期或空字符串","endDate":"原文日期或空字符串","summary":"工作概述","achievements":["职责或成果"],"evidence":"原文摘录"}}],
    "educations":[{{"school":"学校","major":"专业","degree":"学历","startDate":"原文日期或空字符串","endDate":"原文日期或空字符串","evidence":"原文摘录"}}]
  }},
  "projects":[{{"name":"项目名称","summary":"项目背景与目标","role":"个人角色","responsibilities":["职责"],"technologies":["技术"],"achievements":["成果"],"tags":["技术或业务标签"],"startDate":"原文日期或空字符串","endDate":"原文日期或空字符串","evidence":"覆盖该项目的原文摘录"}}]
}}
没有某类信息时使用空字符串或空数组，但仍返回完整顶层结构。

简历原文：
{resume_text}"""

    @staticmethod
    def _call_openai_compatible(
        base_url: str, api_key: str, model_id: str, prompt: str
    ) -> str:
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "你是严格的简历事实提取器。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        result = CloudProjectExtractor._request_json(
            url,
            payload,
            {"Authorization": f"Bearer {api_key}"},
        )
        try:
            return str(result["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("模型返回内容缺少 choices[0].message.content") from error

    @staticmethod
    def _call_anthropic(
        base_url: str,
        api_key: str,
        model_id: str,
        prompt: str,
        max_tokens: int = 4096,
    ) -> str:
        url = base_url if base_url.endswith("/messages") else f"{base_url}/messages"
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        result = CloudProjectExtractor._request_json(
            url,
            payload,
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            return str(result["content"][0]["text"])
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("模型返回内容缺少 content[0].text") from error

    @staticmethod
    def _request_json(url: str, payload: dict[str, object], headers: dict[str, str]) -> dict:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"模型接口返回 HTTP {error.code}: {detail[:300]}") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"模型接口调用失败: {error}") from error

    @staticmethod
    def _parse_projects(content: str) -> list[dict[str, object]]:
        return list(CloudProjectExtractor._parse_resume(content)["projects"])

    @staticmethod
    def _parse_resume(content: str) -> dict[str, object]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            payload = json.loads(cleaned)
            raw_projects = payload if isinstance(payload, list) else payload.get("projects", [])
        except (json.JSONDecodeError, AttributeError) as error:
            raise RuntimeError("模型没有返回合法的简历 JSON") from error
        if not isinstance(raw_projects, list):
            raise RuntimeError("模型返回的 projects 不是数组")

        projects = []
        for item in raw_projects:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                continue
            technologies = CloudProjectExtractor._strings(item.get("technologies"))
            tags = CloudProjectExtractor._strings(item.get("tags"))
            achievements = CloudProjectExtractor._strings(item.get("achievements"))
            responsibilities = CloudProjectExtractor._strings(item.get("responsibilities"))
            projects.append(
                {
                    "name": str(item["name"]).strip(),
                    "data": {
                        "summary": str(item.get("summary", "")).strip(),
                        "role": str(item.get("role", "")).strip(),
                        "responsibilities": responsibilities,
                        "technologies": technologies,
                        "achievements": achievements,
                        "tags": ",".join(dict.fromkeys([*technologies, *tags])),
                        "startDate": str(item.get("startDate", "")).strip(),
                        "endDate": str(item.get("endDate", "")).strip(),
                        "evidence": str(item.get("evidence", "")).strip(),
                        "extractionMethod": "ai",
                    },
                }
            )
        raw_profile = payload.get("profile", {}) if isinstance(payload, dict) else {}
        if raw_profile is None:
            raw_profile = {}
        if not isinstance(raw_profile, dict):
            raise RuntimeError("模型返回的 profile 不是对象")
        return {"profile": CloudProjectExtractor._parse_profile(raw_profile), "projects": projects}

    @staticmethod
    def _parse_profile(raw: dict[str, object]) -> dict[str, object]:
        profile: dict[str, object] = {}
        for key in ("displayName", "targetRoles", "yearsExperience", "cities", "phone", "email"):
            value = str(raw.get(key, "")).strip()
            if value:
                profile[key] = value

        strengths = []
        raw_strengths = raw.get("strengths", [])
        for index, item in enumerate(
            raw_strengths if isinstance(raw_strengths, list) else [], 1
        ):
            if isinstance(item, dict):
                content = str(item.get("content", "")).strip()
                evidence = str(item.get("evidence", "")).strip()
            else:
                content, evidence = str(item).strip(), ""
            if content:
                strengths.append(
                    {"id": f"strength-{index}", "content": content, "evidence": evidence}
                )
        if strengths:
            profile["strengths"] = strengths
            profile["summary"] = "\n".join(item["content"] for item in strengths)

        groups = []
        raw_groups = raw.get("techStackGroups", [])
        for index, item in enumerate(
            raw_groups if isinstance(raw_groups, list) else [], 1
        ):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "技术栈")).strip() or "技术栈"
            values = CloudProjectExtractor._strings(item.get("items"))
            if values:
                groups.append({"id": f"tech-{index}", "name": name, "items": values})
        if groups:
            profile["techStackGroups"] = groups
            profile["techStack"] = "\n".join(
                f"{item['name']}：{'、'.join(item['items'])}" for item in groups
            )

        for source_key, target_key, text_key, prefix in (
            ("workExperiences", "workExperiences", "workExperience", "work"),
            ("educations", "educations", "education", "education"),
        ):
            entities = []
            raw_entities = raw.get(source_key, [])
            for index, item in enumerate(raw_entities if isinstance(raw_entities, list) else [], 1):
                if not isinstance(item, dict):
                    continue
                entity = {key: value for key, value in item.items() if value not in (None, "", [])}
                if not entity:
                    continue
                entity["id"] = f"{prefix}-{index}"
                entity["content"] = CloudProjectExtractor._entity_text(entity)
                entities.append(entity)
            if entities:
                profile[target_key] = entities
                profile[text_key] = "\n\n".join(str(item["content"]) for item in entities)
        return profile

    @staticmethod
    def _entity_text(entity: dict[str, object]) -> str:
        labels = {
            "company": "公司", "role": "职位", "school": "学校", "major": "专业",
            "degree": "学历", "startDate": "开始时间", "endDate": "结束时间",
            "summary": "概述", "achievements": "职责与成果", "evidence": "原文证据",
        }
        return "\n".join(
            f"{labels.get(key, key)}：{CloudProjectExtractor._text(value)}"
            for key, value in entity.items()
            if key not in ("id", "content") and value not in (None, "", [])
        )

    @staticmethod
    def _text(value: object) -> str:
        if isinstance(value, list):
            return "、".join(str(item) for item in value)
        return str(value)

    @staticmethod
    def _strings(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class CloudMaterialPreviewGenerator:
    """基于已配置模型生成只读的问候语和简历组成预览。"""

    def __init__(self, library: LibraryRepository) -> None:
        self.library = library

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        prompt = self._prompt(context)
        errors: list[str] = []
        for record in _model_candidates(self.library, model_record_id):
            try:
                model_id, api_key, base_url, provider = _model_settings(record["data"])
                if provider == "Anthropic":
                    content = CloudProjectExtractor._call_anthropic(
                        base_url, api_key, model_id, prompt
                    )
                else:
                    content = CloudProjectExtractor._call_openai_compatible(
                        base_url, api_key, model_id, prompt
                    )
                result = self._parse(content)
                return {
                    **result,
                    "modelRecordId": record["id"],
                    "modelName": record["name"],
                    "modelId": model_id,
                    "attemptErrors": errors,
                }
            except RuntimeError as error:
                errors.append(f"{record['name']}：{error}")
        raise RuntimeError("；".join(errors))

    @staticmethod
    def _prompt(context: dict[str, object]) -> str:
        return f"""你是求职材料编排器。请仅使用输入中的真实事实，不得虚构经历、指标、学历或技能。
结合职位 JD、个人档案、本地资料匹配证据、默认问候语和默认简历，生成一次只读测试预览。
问候语应自然、简短，并明确体现最相关的真实经历；简历只做内容选取和顺序编排。
只返回 JSON，不要 Markdown，格式必须为：
{{"greeting":"新问候语","resume":{{"headline":"目标标题","summary":["优势条目"],"skills":["技能"],"projects":["项目及匹配说明"],"workExperience":["工作经历"],"education":["教育经历"],"optimizationNotes":["为何这样编排"]}}}}

输入：
{json.dumps(context, ensure_ascii=False)}"""

    @staticmethod
    def _parse(content: str) -> dict[str, object]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise RuntimeError("模型没有返回合法的材料预览 JSON") from error
        if not isinstance(payload, dict) or not str(payload.get("greeting", "")).strip():
            raise RuntimeError("模型返回内容缺少 greeting")
        resume = payload.get("resume")
        if not isinstance(resume, dict) or not str(resume.get("headline", "")).strip():
            raise RuntimeError("模型返回内容缺少 resume.headline")
        normalized_resume = {"headline": str(resume["headline"]).strip()}
        for key in (
            "summary",
            "skills",
            "projects",
            "workExperience",
            "education",
            "optimizationNotes",
        ):
            normalized_resume[key] = CloudProjectExtractor._strings(resume.get(key))
        return {"greeting": str(payload["greeting"]).strip(), "resume": normalized_resume}


class CloudJobAnalysisGenerator:
    """基于已配置模型对职位和候选人真实材料做只读分析。"""

    def __init__(self, library: LibraryRepository) -> None:
        self.library = library

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        prompt = self._prompt(context)
        errors: list[str] = []
        for record in _model_candidates(self.library, model_record_id):
            try:
                model_id, api_key, base_url, provider = _model_settings(record["data"])
                if provider == "Anthropic":
                    content = CloudProjectExtractor._call_anthropic(
                        base_url, api_key, model_id, prompt
                    )
                else:
                    content = CloudProjectExtractor._call_openai_compatible(
                        base_url, api_key, model_id, prompt
                    )
                result = self._parse(content)
                return {
                    **result,
                    "modelRecordId": record["id"],
                    "modelName": record["name"],
                    "modelId": model_id,
                    "attemptErrors": errors,
                }
            except RuntimeError as error:
                errors.append(f"{record['name']}：{error}")
        raise RuntimeError("；".join(errors))

    @staticmethod
    def _prompt(context: dict[str, object]) -> str:
        return f"""你是谨慎的求职职位分析顾问。
请结合职位 JD、候选人档案、本地资料匹配证据和本地匹配结果做分析。
只能使用输入中的真实事实，不得虚构候选人的经历、技能、年限、学历、指标或公司信息。证据不足时必须明确说明。
建议应具体、可执行，面试问题用于帮助候选人准备，不要替候选人编造答案。
只返回 JSON，不要 Markdown，格式必须为：
{{"summary":"整体判断","strengths":["有证据的优势"],"gaps":["差距或待核实项"],"recommendations":["行动建议"],"interviewQuestions":["建议准备的问题"]}}

输入：
{json.dumps(context, ensure_ascii=False)}"""

    @staticmethod
    def _parse(content: str) -> dict[str, object]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise RuntimeError("模型没有返回合法的职位分析 JSON") from error
        if not isinstance(payload, dict) or not str(payload.get("summary", "")).strip():
            raise RuntimeError("模型返回内容缺少 summary")
        return {
            "summary": str(payload["summary"]).strip(),
            "strengths": CloudProjectExtractor._strings(payload.get("strengths")),
            "gaps": CloudProjectExtractor._strings(payload.get("gaps")),
            "recommendations": CloudProjectExtractor._strings(
                payload.get("recommendations")
            ),
            "interviewQuestions": CloudProjectExtractor._strings(
                payload.get("interviewQuestions")
            ),
        }


class CloudGreetingGenerator:
    """使用主模型和兜底模型，仅生成职位问候语。"""

    def __init__(self, library: LibraryRepository) -> None:
        self.library = library

    def generate(
        self, context: dict[str, object], model_record_id: int | None = None
    ) -> dict[str, object]:
        prompt = self._prompt(context)
        errors: list[str] = []
        for record in _model_candidates(self.library, model_record_id):
            try:
                model_id, api_key, base_url, provider = _model_settings(record["data"])
                if provider == "Anthropic":
                    content = CloudProjectExtractor._call_anthropic(
                        base_url, api_key, model_id, prompt
                    )
                else:
                    content = CloudProjectExtractor._call_openai_compatible(
                        base_url, api_key, model_id, prompt
                    )
                return {
                    "greeting": self._parse(content),
                    "modelRecordId": record["id"],
                    "modelName": record["name"],
                    "modelId": model_id,
                    "attemptErrors": errors,
                }
            except RuntimeError as error:
                errors.append(f"{record['name']}：{error}")
        raise RuntimeError("；".join(errors))

    @staticmethod
    def _prompt(context: dict[str, object]) -> str:
        return f"""你是求职问候语生成器。
请结合职位 JD、个人档案、本地资料匹配证据和默认问候语，生成一条适合首次联系招聘者的中文问候语。
要求：
1. 只能使用输入中存在的真实经历、技能和项目，不得虚构事实、年限、指标、学历或公司经历。
2. 优先选择与 JD 最相关的 1 至 2 项真实能力，不堆砌关键词。
3. 语气自然、礼貌、简洁，建议 60 至 120 个汉字，不输出简历、不解释生成过程。
4. 如果证据不足，在默认问候语基础上做轻量改写，不补造信息。
只返回 JSON，不要 Markdown，格式必须为：
{{"greeting":"问候语"}}

输入：
{json.dumps(context, ensure_ascii=False)}"""

    @staticmethod
    def _parse(content: str) -> str:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise RuntimeError("模型没有返回合法的问候语 JSON") from error
        greeting = str(payload.get("greeting", "")).strip() if isinstance(payload, dict) else ""
        if not greeting:
            raise RuntimeError("模型返回内容缺少 greeting")
        return greeting
