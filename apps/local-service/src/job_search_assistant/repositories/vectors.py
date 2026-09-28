import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class VectorRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(source_type, source_id, chunk_index)
                )
                """
            )

    def replace_all(
        self, chunks: list[dict[str, Any]], vectors: list[list[float]], model: str
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunk and vector counts must match")
        self.initialize()
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM vector_chunks")
            connection.executemany(
                """
                INSERT INTO vector_chunks(
                    source_type, source_id, source_name, chunk_index, content,
                    content_hash, embedding_json, model, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk["source_type"], chunk["source_id"], chunk["source_name"],
                        chunk["chunk_index"], chunk["content"],
                        hashlib.sha256(chunk["content"].encode()).hexdigest(),
                        json.dumps(vector), model, now,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
        return len(chunks)

    def status(self) -> dict[str, Any]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """SELECT COUNT(*), COUNT(DISTINCT source_type || ':' || source_id),
                MAX(indexed_at), MAX(model) FROM vector_chunks"""
            ).fetchone()
        return {"chunks": row[0], "sources": row[1], "indexedAt": row[2], "model": row[3]}

    def search(self, query_vector: list[float], limit: int) -> list[dict[str, Any]]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM vector_chunks").fetchall()
        scored = []
        for row in rows:
            vector = json.loads(row["embedding_json"])
            score = self._cosine(query_vector, vector)
            scored.append({
                "sourceType": row["source_type"], "sourceId": row["source_id"],
                "sourceName": row["source_name"], "chunkIndex": row["chunk_index"],
                "content": row["content"], "score": round(score, 6),
            })
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        norm = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        return dot / norm if norm else 0.0
