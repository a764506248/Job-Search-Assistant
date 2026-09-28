import uvicorn
from fastapi import FastAPI

from . import __version__
from .api import router
from .config import settings

app = FastAPI(
    title="Job Search Assistant Local Service",
    version=__version__,
    docs_url="/docs",
    redoc_url=None,
)
app.include_router(router)


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
