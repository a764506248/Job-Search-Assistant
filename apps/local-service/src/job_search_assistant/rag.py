import json
import re
from typing import Any

from .embedding import Embedder
from .repositories import LibraryRepository, VectorRepository


class RagService:
    def __init__(
        self,
        library: LibraryRepository,
        vectors: VectorRepository,
        embedder: Embedder,
    ) -> None:
        self.library = library
        self.vectors = vectors
        self.embedder = embedder

    def status(self) -> dict[str, Any]:
        index = self.vectors.status()
        try:
            service = self.embedder.health()
            available = service.get("status") == "ok"
        except RuntimeError:
            service = {"status": "offline", "model": self.embedder.model}
            available = False
        return {**index, "embeddingAvailable": available, "embeddingService": service}

    def rebuild(self) -> dict[str, Any]:
        if self.embedder.health().get("status") != "ok":
            raise RuntimeError("embedding service is not ready")
        chunks = self._collect_knowledge_units()
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), 32):
            batch = [item["content"] for item in chunks[start : start + 32]]
            vectors.extend(self.embedder.embed(batch))
        count = self.vectors.replace_all(chunks, vectors, self.embedder.model)
        return {**self.vectors.status(), "rebuilt": count}

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        query_vector = self.embedder.embed([query])[0]
        return self.vectors.search_hybrid(query, query_vector, limit)

    def list_chunks(self) -> list[dict[str, Any]]:
        return self.vectors.list_all()

    def delete_chunk(self, chunk_id: int) -> bool:
        return self.vectors.delete(chunk_id)

    def _collect_knowledge_units(self) -> list[dict[str, Any]]:
        """Build vectors by resume section; projects remain independently addressable."""
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
                    "profile", "strengths", "个人优势", "strengths", "strengths",
                    "\n".join(strengths), [],
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
                    "profile", "tech-stack", "技术栈", "tech-stack", "tech-stack",
                    "\n".join(tech_lines), tech_tags,
                )
            )

        for field, knowledge_type, label in (
            ("workExperiences", "work-experience", "工作经历"),
            ("educations", "education", "教育经历"),
        ):
            contents: list[str] = []
            for entity in profile.get(field, []):
                content = self._to_text(entity.get("content") or entity).strip()
                if content:
                    contents.append(content)
            if contents:
                units.append(
                    self._unit(
                        "profile", knowledge_type, label, knowledge_type,
                        knowledge_type, "\n\n".join(contents), [],
                    )
                )

        for record in self.library.list("projects"):
            data = record["data"]
            if self._is_legacy_aggregate_project(record["name"], data):
                continue
            content = f"项目名称：{record['name']}\n{self._project_text(data)}"
            tags = self._tags(data, content)
            units.append(
                self._unit(
                    "projects",
                    str(record["id"]),
                    record["name"],
                    "project",
                    str(record["id"]),
                    content,
                    tags,
                )
            )
        return units

    @staticmethod
    def _is_legacy_aggregate_project(name: str, data: dict[str, Any]) -> bool:
        """Exclude old fallback records that contain an entire resume project section."""
        return (
            data.get("source") == "resume-import"
            and data.get("extractionMethod") != "ai"
            and name.strip().endswith("· 项目经历")
        )

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
            "source_type": source_type,
            "source_id": source_id,
            "source_name": source_name,
            "knowledge_type": knowledge_type,
            "entity_id": entity_id,
            "tags": list(dict.fromkeys(tag for tag in tags if tag)),
            "chunk_index": 0,
            "content": content,
        }

    @staticmethod
    def _project_text(data: dict[str, Any]) -> str:
        ordered = (
            "summary", "role", "responsibilities", "technologies", "achievements",
            "startDate", "endDate",
        )
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
            f"{labels[key]}：{RagService._to_text(data[key])}"
            for key in ordered
            if data.get(key) not in (None, "", [])
        )

    @staticmethod
    def _tags(data: dict[str, Any], content: str) -> list[str]:
        explicit = data.get("tags", [])
        if isinstance(explicit, str):
            tags = [item.strip() for item in re.split(r"[,，/|]", explicit) if item.strip()]
        elif isinstance(explicit, list):
            tags = [str(item).strip() for item in explicit if str(item).strip()]
        else:
            tags = []
        technologies = data.get("technologies", [])
        if isinstance(technologies, str):
            tags.extend(
                item.strip() for item in re.split(r"[,，/|]", technologies) if item.strip()
            )
        elif isinstance(technologies, list):
            tags.extend(str(item).strip() for item in technologies if str(item).strip())
        return list(dict.fromkeys(tags))

    @staticmethod
    def _to_text(value: Any) -> str:
        if isinstance(value, dict):
            return "\n".join(
                f"{key}：{RagService._to_text(item)}"
                for key, item in value.items()
                if item not in (None, "", [])
            )
        if isinstance(value, list):
            return "、".join(RagService._to_text(item) for item in value)
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return json.dumps(value, ensure_ascii=False)
