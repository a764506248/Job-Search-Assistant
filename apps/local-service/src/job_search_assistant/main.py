import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import create_router
from .automation.browser_protocol import BrowserConnectionHub
from .config import settings
from .knowledge import KnowledgeSearchService
from .project_extraction import (
    CloudGreetingGenerator,
    CloudJobAnalysisGenerator,
    CloudMaterialPreviewGenerator,
    CloudModelConnectionTester,
    CloudProjectExtractor,
    GreetingGenerator,
    JobAnalysisGenerator,
    MaterialPreviewGenerator,
    ModelConnectionTester,
    ProjectExtractor,
)
from .repositories import (
    AutomationRepository,
    AuthRepository,
    ClientLogRepository,
    DeliveryRepository,
    JobRepository,
    LibraryRepository,
)

ALLOWED_EXTENSION_ORIGIN = re.compile(
    r"^(?:(?:chrome|moz)-extension://.+|https://(?:[a-z0-9-]+\.)?zhipin\.com)$"
)


def create_app(
    database_path: Path | None = None,
    project_extractor: ProjectExtractor | None = None,
    model_tester: ModelConnectionTester | None = None,
    material_preview_generator: MaterialPreviewGenerator | None = None,
    greeting_generator: GreetingGenerator | None = None,
    job_analysis_generator: JobAnalysisGenerator | None = None,
    browser_hub: BrowserConnectionHub | None = None,
    **_unused_dependencies: object,
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
        allow_headers=["Content-Type", "Authorization", "X-Local-Token"],
        allow_private_network=True,
    )
    resolved_database_path = database_path or settings.data_dir / "jobs.sqlite3"
    # 暴露数据文件位置，便于本地脚本与测试直接准备数据（不经过 HTTP 层）。
    application.state.database_path = resolved_database_path
    job_repository = JobRepository(resolved_database_path)
    library_repository = LibraryRepository(resolved_database_path)
    client_log_repository = ClientLogRepository(resolved_database_path)
    delivery_repository = DeliveryRepository(resolved_database_path)
    automation_repository = AutomationRepository(resolved_database_path)
    auth_repository = AuthRepository(resolved_database_path)
    resolved_browser_hub = browser_hub or BrowserConnectionHub(
        resolved_database_path.parent / "browser-token.sha256"
    )
    knowledge_search = KnowledgeSearchService(library_repository)
    resolved_project_extractor = project_extractor or CloudProjectExtractor(library_repository)
    resolved_model_tester = model_tester or CloudModelConnectionTester()
    resolved_material_generator = material_preview_generator or CloudMaterialPreviewGenerator(
        library_repository
    )
    resolved_greeting_generator = greeting_generator or CloudGreetingGenerator(library_repository)
    resolved_job_analysis_generator = job_analysis_generator or CloudJobAnalysisGenerator(
        library_repository
    )
    application.include_router(
        create_router(
            job_repository,
            library_repository,
            client_log_repository,
            delivery_repository,
            knowledge_search,
            resolved_project_extractor,
            resolved_model_tester,
            resolved_material_generator,
            resolved_greeting_generator,
            resolved_job_analysis_generator,
            resolved_database_path.parent / "resume-images",
            automation_repository,
            resolved_browser_hub,
            auth_repository,
        )
    )
    return application


app = create_app()


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
