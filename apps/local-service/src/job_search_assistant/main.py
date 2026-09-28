import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import create_router
from .config import settings
from .embedding import Embedder, HttpEmbeddingClient
from .rag import RagService
from .repositories import JobRepository, LibraryRepository, VectorRepository

DASHBOARD_ROUTES = {
    "jobs",
    "profile",
    "projects",
    "resumes",
    "templates",
    "rules",
    "models",
    "knowledge",
}

ALLOWED_EXTENSION_ORIGIN = re.compile(
    r"^(?:(?:chrome|moz)-extension://.+|https://(?:[a-z0-9-]+\.)?zhipin\.com)$"
)


def create_app(database_path: Path | None = None, embedder: Embedder | None = None) -> FastAPI:
    application = FastAPI(
        title="Job Search Assistant Local Service",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ALLOWED_EXTENSION_ORIGIN.pattern,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Local-Token"],
        allow_private_network=True,
    )
    resolved_database_path = database_path or settings.data_dir / "jobs.sqlite3"
    job_repository = JobRepository(resolved_database_path)
    library_repository = LibraryRepository(resolved_database_path)
    vector_repository = VectorRepository(resolved_database_path)
    resolved_embedder = embedder or HttpEmbeddingClient(
        settings.embedding_url, settings.embedding_model
    )
    rag_service = RagService(library_repository, vector_repository, resolved_embedder)
    application.include_router(create_router(job_repository, library_repository, rag_service))
    static_dir = Path(__file__).parent / "static"
    application.mount("/assets", StaticFiles(directory=static_dir), name="dashboard-assets")

    @application.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @application.get("/{view_name}", include_in_schema=False)
    def dashboard_view(view_name: str) -> FileResponse:
        if view_name not in DASHBOARD_ROUTES:
            raise HTTPException(status_code=404, detail="page not found")
        return FileResponse(static_dir / "index.html")

    return application


app = create_app()


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
