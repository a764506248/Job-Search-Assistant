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
        """Build one vector per resume entity; never split raw resume text by length."""
        units: list[dict[str, Any]] = []
        profile = self.library.get_profile()
        for index, strength in enumerate(profile.get("strengths", []), 1):
            entity_id = str(strength.get("id") or f"strength-{index}")
            content = str(strength.get("content", "")).strip()
            if content:
                units.append(
                    self._unit(
                        "profile", entity_id, f"个人优势 #{index}",
                        "strengths", entity_id, content, [],
                    )
                )

        for index, group in enumerate(profile.get("techStackGroups", []), 1):
            entity_id = str(group.get("id") or f"tech-{index}")
            name = str(group.get("name") or f"技术栈 #{index}")
            items = [str(item).strip() for item in group.get("items", []) if str(item).strip()]
            if items:
                units.append(
                    self._unit(
                        "profile", entity_id, name, "tech-stack", entity_id,
                        f"{name}：{'、'.join(items)}", items,
                    )
                )

        for field, knowledge_type, label in (
            ("workExperiences", "work-experience", "工作经历"),
            ("educations", "education", "教育经历"),
        ):
            for index, entity in enumerate(profile.get(field, []), 1):
                entity_id = str(entity.get("id") or f"{knowledge_type}-{index}")
                content = self._to_text(entity.get("content") or entity)
                if content:
                    units.append(
                        self._unit(
                            "profile", entity_id, f"{label} #{index}", knowledge_type,
                            entity_id, content, [],
                        )
                    )

        for record in self.library.list("projects"):
            data = record["data"]
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
