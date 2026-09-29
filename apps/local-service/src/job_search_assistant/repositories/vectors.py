import hashlib
import json
import math
import re
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
                    knowledge_type TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
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
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(vector_chunks)").fetchall()
            }
            for name, definition in (
                ("knowledge_type", "TEXT NOT NULL DEFAULT ''"),
                ("entity_id", "TEXT NOT NULL DEFAULT ''"),
                ("tags_json", "TEXT NOT NULL DEFAULT '[]'"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE vector_chunks ADD COLUMN {name} {definition}")
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS vector_chunks_fts
                USING fts5(source_name, content, tokenize='trigram')
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
            connection.execute("DELETE FROM vector_chunks_fts")
            connection.executemany(
                """
                INSERT INTO vector_chunks(
                    source_type, source_id, source_name, knowledge_type, entity_id,
                    tags_json, chunk_index, content,
                    content_hash, embedding_json, model, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk["source_type"],
                        chunk["source_id"],
                        chunk["source_name"],
                        chunk["knowledge_type"],
                        chunk["entity_id"],
                        json.dumps(chunk["tags"], ensure_ascii=False),
                        chunk["chunk_index"],
                        chunk["content"],
                        hashlib.sha256(chunk["content"].encode()).hexdigest(),
                        json.dumps(vector),
                        model,
                        now,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
            rows = connection.execute(
                "SELECT id, source_name, content FROM vector_chunks"
            ).fetchall()
            connection.executemany(
                "INSERT INTO vector_chunks_fts(rowid, source_name, content) VALUES (?, ?, ?)",
                rows,
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
            scored.append(
                {
                    "sourceType": row["source_type"],
                    "sourceId": row["source_id"],
                    "sourceName": row["source_name"],
                    "knowledgeType": row["knowledge_type"],
                    "entityId": row["entity_id"],
                    "tags": json.loads(row["tags_json"]),
                    "chunkIndex": row["chunk_index"],
                    "content": row["content"],
                    "score": round(score, 6),
                }
            )
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    def search_hybrid(
        self, query: str, query_vector: list[float], limit: int
    ) -> list[dict[str, Any]]:
        """Merge semantic and FTS5/BM25 recall using normalized weighted scores."""
        self.initialize()
        candidate_limit = max(limit * 4, 20)
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM vector_chunks").fetchall()
            fts_query = self._fts_query(query)
            try:
                keyword_rows = connection.execute(
                    """SELECT rowid, bm25(vector_chunks_fts) AS rank
                    FROM vector_chunks_fts WHERE vector_chunks_fts MATCH ?
                    ORDER BY rank LIMIT ?""",
                    (fts_query, candidate_limit),
                ).fetchall() if fts_query else []
            except sqlite3.OperationalError:
                keyword_rows = []

        keyword_raw = {int(row["rowid"]): max(0.0, -float(row["rank"])) for row in keyword_rows}
        max_keyword = max(keyword_raw.values(), default=0.0)
        scored: list[dict[str, Any]] = []
        for row in rows:
            vector_score = max(0.0, self._cosine(query_vector, json.loads(row["embedding_json"])))
            keyword_score = (
                keyword_raw.get(int(row["id"]), 0.0) / max_keyword if max_keyword else 0.0
            )
            combined = vector_score * 0.7 + keyword_score * 0.3
            scored.append(
                {
                    "sourceType": row["source_type"],
                    "sourceId": row["source_id"],
                    "sourceName": row["source_name"],
                    "knowledgeType": row["knowledge_type"],
                    "entityId": row["entity_id"],
                    "tags": json.loads(row["tags_json"]),
                    "chunkIndex": row["chunk_index"],
                    "content": row["content"],
                    "score": round(combined, 6),
                    "vectorScore": round(vector_score, 6),
                    "keywordScore": round(keyword_score, 6),
                }
            )
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    @staticmethod
    def _fts_query(query: str) -> str:
        terms: list[str] = []
        terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_.+#-]{1,30}", query))
        for phrase in re.findall(r"[\u4e00-\u9fff]{3,}", query):
            terms.extend(phrase[index : index + 3] for index in range(len(phrase) - 2))
        unique = list(dict.fromkeys(term.lower() for term in terms if len(term) >= 3))[:24]
        return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in unique)

    def list_all(self) -> list[dict[str, Any]]:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT * FROM vector_chunks
                ORDER BY source_type, source_name, chunk_index, id"""
            ).fetchall()
        items = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            items.append(
                {
                    "id": row["id"],
                    "sourceType": row["source_type"],
                    "sourceId": row["source_id"],
                    "sourceName": row["source_name"],
                    "knowledgeType": row["knowledge_type"],
                    "entityId": row["entity_id"],
                    "tags": json.loads(row["tags_json"]),
                    "chunkIndex": row["chunk_index"],
                    "content": row["content"],
                    "contentHash": row["content_hash"],
                    "embedding": embedding,
                    "dimensions": len(embedding),
                    "model": row["model"],
                    "indexedAt": row["indexed_at"],
                }
            )
        return items

    def delete(self, chunk_id: int) -> bool:
        self.initialize()
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute("DELETE FROM vector_chunks WHERE id = ?", (chunk_id,))
            connection.execute("DELETE FROM vector_chunks_fts WHERE rowid = ?", (chunk_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        norm = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        return dot / norm if norm else 0.0
