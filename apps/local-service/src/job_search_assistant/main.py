from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import create_router
from .config import settings
from .repositories import JobRepository


def create_app(database_path: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="Job Search Assistant Local Service",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome|moz)-extension://.+$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Local-Token"],
    )
    repository = JobRepository(database_path or settings.data_dir / "jobs.sqlite3")
    application.include_router(create_router(repository))
    return application


app = create_app()


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
