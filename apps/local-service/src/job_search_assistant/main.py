import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import create_router
from .config import settings
from .embedding import Embedder, HttpEmbeddingClient
from .project_extraction import (
    CloudGreetingGenerator,
    CloudMaterialPreviewGenerator,
    CloudModelConnectionTester,
    CloudProjectExtractor,
    GreetingGenerator,
    MaterialPreviewGenerator,
    ModelConnectionTester,
    ProjectExtractor,
)
from .rag import RagService
from .repositories import (
    AutomationRepository,
    ClientLogRepository,
    DeliveryRepository,
    JobRepository,
    LibraryRepository,
    VectorRepository,
)

ALLOWED_EXTENSION_ORIGIN = re.compile(
    r"^(?:(?:chrome|moz)-extension://.+|https://(?:[a-z0-9-]+\.)?zhipin\.com)$"
)


def create_app(
    database_path: Path | None = None,
    embedder: Embedder | None = None,
    project_extractor: ProjectExtractor | None = None,
    model_tester: ModelConnectionTester | None = None,
    material_preview_generator: MaterialPreviewGenerator | None = None,
    greeting_generator: GreetingGenerator | None = None,
) -> FastAPI:
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
    client_log_repository = ClientLogRepository(resolved_database_path)
    delivery_repository = DeliveryRepository(resolved_database_path)
    automation_repository = AutomationRepository(resolved_database_path)
    resolved_embedder = embedder or HttpEmbeddingClient(
        settings.embedding_url, settings.embedding_model
    )
    rag_service = RagService(library_repository, vector_repository, resolved_embedder)
    resolved_project_extractor = project_extractor or CloudProjectExtractor(library_repository)
    resolved_model_tester = model_tester or CloudModelConnectionTester()
    resolved_material_generator = material_preview_generator or CloudMaterialPreviewGenerator(
        library_repository
    )
    resolved_greeting_generator = greeting_generator or CloudGreetingGenerator(library_repository)
    application.include_router(
        create_router(
            job_repository,
            library_repository,
            client_log_repository,
            delivery_repository,
            rag_service,
            resolved_project_extractor,
            resolved_model_tester,
            resolved_material_generator,
            resolved_greeting_generator,
            resolved_database_path.parent / "resume-images",
            automation_repository,
        )
    )
    return application


app = create_app()


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
