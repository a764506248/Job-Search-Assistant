import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastembed import TextEmbedding
from pydantic import BaseModel, Field

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "jinaai/jina-embeddings-v2-base-zh")
model: TextEmbedding | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model
    model = TextEmbedding(model_name=MODEL_NAME)
    yield
    model = None


app = FastAPI(title="Job Search Assistant Embedding Service", lifespan=lifespan)


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok" if model is not None else "loading", "model": MODEL_NAME}


@app.post("/embed")
def embed(request: EmbeddingRequest) -> dict[str, object]:
    if model is None:
        raise RuntimeError("model is not loaded")
    vectors = [vector.tolist() for vector in model.embed(request.texts)]
    return {"model": MODEL_NAME, "dimensions": len(vectors[0]), "vectors": vectors}
