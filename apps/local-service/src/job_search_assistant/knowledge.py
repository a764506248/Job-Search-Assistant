import json
import re
from typing import Any

from .repositories import LibraryRepository


class KnowledgeSearchService:
    """Search structured local facts directly without a derived index."""

    def __init__(self, library: LibraryRepository) -> None:
        self.library = library

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []
        ranked: list[dict[str, Any]] = []
        for unit in self._collect_knowledge_units():
            searchable = "\n".join([unit["content"], *unit["tags"]])
            content_tokens = self._tokens(searchable)
            overlap = query_tokens & content_tokens
            if not overlap:
                continue
            # Three shared technical/Chinese terms are already strong evidence for a
            # small local profile. This intentionally avoids corpus-size-dependent
            # scoring now that there is no vector index.
            score = min(1.0, len(overlap) / 3)
            ranked.append(
                {
                    **unit,
                    "score": round(score, 6),
                    "keywordScore": round(score, 6),
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["sourceName"])))
        return ranked[:limit]

    def _collect_knowledge_units(self) -> list[dict[str, Any]]:
        units: list[dict[str, Any]] = []
        profile = self.library.get_profile()
        strengths = [
            str(item.get("content", "")).strip()
            for item in profile.get("strengths", [])
            if str(item.get("content", "")).strip()
        ]
        if strengths:
            units.append(
                self._unit(
                    "profile",
                    "strengths",
                    "个人优势",
                    "strengths",
                    "strengths",
                    "\n".join(strengths),
                    [],
                )
            )

        tech_lines: list[str] = []
        tech_tags: list[str] = []
        for group in profile.get("techStackGroups", []):
            name = str(group.get("name") or "技术栈").strip()
            items = [str(item).strip() for item in group.get("items", []) if str(item).strip()]
            if items:
                tech_lines.append(f"{name}：{'、'.join(items)}")
                tech_tags.extend(items)
        if tech_lines:
            units.append(
                self._unit(
                    "profile",
                    "tech-stack",
                    "技术栈",
                    "tech-stack",
                    "tech-stack",
                    "\n".join(tech_lines),
                    tech_tags,
                )
            )

        for field, knowledge_type, label in (
            ("workExperiences", "work-experience", "工作经历"),
            ("educations", "education", "教育经历"),
        ):
            contents = [
                self._to_text(entity.get("content") or entity).strip()
                for entity in profile.get(field, [])
                if self._to_text(entity.get("content") or entity).strip()
            ]
            if contents:
                units.append(
                    self._unit(
                        "profile",
                        knowledge_type,
                        label,
                        knowledge_type,
                        knowledge_type,
                        "\n\n".join(contents),
                        [],
                    )
                )

        for record in self.library.list("projects"):
            data = record["data"]
            if self._is_legacy_aggregate_project(record["name"], data):
                continue
            content = f"项目名称：{record['name']}\n{self._project_text(data)}"
            units.append(
                self._unit(
                    "projects",
                    str(record["id"]),
                    record["name"],
                    "project",
                    str(record["id"]),
                    content,
                    self._tags(data),
                )
            )
        return units

    @staticmethod
    def _unit(
        source_type: str,
        source_id: str,
        source_name: str,
        knowledge_type: str,
        entity_id: str,
        content: str,
        tags: list[str],
    ) -> dict[str, Any]:
        return {
            "sourceType": source_type,
            "sourceId": source_id,
            "sourceName": source_name,
            "knowledgeType": knowledge_type,
            "entityId": entity_id,
            "tags": list(dict.fromkeys(tag for tag in tags if tag)),
            "chunkIndex": 0,
            "content": content,
        }

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = text.lower()
        tokens = set(re.findall(r"[a-z0-9][a-z0-9+#.\-]{1,}", normalized))
        for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
            if len(sequence) <= 2:
                tokens.add(sequence)
            else:
                tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
        return tokens

    @staticmethod
    def _is_legacy_aggregate_project(name: str, data: dict[str, Any]) -> bool:
        return (
            data.get("source") == "resume-import"
            and data.get("extractionMethod") != "ai"
            and name.strip().endswith("· 项目经历")
        )

    @staticmethod
    def _project_text(data: dict[str, Any]) -> str:
        labels = {
            "summary": "项目说明",
            "role": "职责",
            "responsibilities": "职责明细",
            "technologies": "技术栈",
            "achievements": "成果",
            "startDate": "开始时间",
            "endDate": "结束时间",
        }
        return "\n".join(
            f"{labels[key]}：{KnowledgeSearchService._to_text(data[key])}"
            for key in labels
            if data.get(key) not in (None, "", [])
        )

    @staticmethod
    def _tags(data: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for field in ("tags", "technologies"):
            raw = data.get(field, [])
            if isinstance(raw, str):
                values.extend(item.strip() for item in re.split(r"[,，/|]", raw) if item.strip())
            elif isinstance(raw, list):
                values.extend(str(item).strip() for item in raw if str(item).strip())
        return list(dict.fromkeys(values))

    @staticmethod
    def _to_text(value: Any) -> str:
        if isinstance(value, dict):
            return "\n".join(
                f"{key}：{KnowledgeSearchService._to_text(item)}"
                for key, item in value.items()
                if item not in (None, "", [])
            )
        if isinstance(value, list):
            return "、".join(KnowledgeSearchService._to_text(item) for item in value)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return json.dumps(value, ensure_ascii=False)
