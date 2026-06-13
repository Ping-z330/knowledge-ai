from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from .config import get_settings
from .database import init_db
from .routers.knowledge_bases import router as knowledge_bases_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(knowledge_bases_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "Knowledge Agent backend is running"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

