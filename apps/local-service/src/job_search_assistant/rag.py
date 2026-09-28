import json
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
        chunks = self._collect_chunks()
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), 32):
            batch = [item["content"] for item in chunks[start : start + 32]]
            vectors.extend(self.embedder.embed(batch))
        count = self.vectors.replace_all(chunks, vectors, self.embedder.model)
        return {**self.vectors.status(), "rebuilt": count}

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        query_vector = self.embedder.embed([query])[0]
        return self.vectors.search(query_vector, limit)

    def list_chunks(self) -> list[dict[str, Any]]:
        return self.vectors.list_all()

    def _collect_chunks(self) -> list[dict[str, Any]]:
        sources: list[tuple[str, str, str, str]] = []
        profile = self.library.get_profile()
        if profile:
            sources.append(("profile", "profile", "个人档案", self._to_text(profile)))
        for kind in ("projects", "resumes"):
            for record in self.library.list(kind):
                content = f"名称：{record['name']}\n{self._to_text(record['data'])}"
                sources.append((kind, str(record["id"]), record["name"], content))

        chunks = []
        for source_type, source_id, source_name, content in sources:
            for index, text in enumerate(self._chunk(content)):
                chunks.append(
                    {
                        "source_type": source_type,
                        "source_id": source_id,
                        "source_name": source_name,
                        "chunk_index": index,
                        "content": text,
                    }
                )
        return chunks

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

    @staticmethod
    def _chunk(text: str, size: int = 500, overlap: int = 80) -> list[str]:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not normalized:
            return []
        chunks = []
        start = 0
        while start < len(normalized):
            chunks.append(normalized[start : start + size])
            if start + size >= len(normalized):
                break
            start += size - overlap
        return chunks
