import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import connection_scope, init_db
from .logging_config import setup_logging
from .routers.knowledge_bases import router as knowledge_bases_router

_logger = logging.getLogger(__name__)


def _recover_stuck_documents() -> None:
    """将服务重启后卡在 running 状态的文档标记为 failed。"""
    with connection_scope() as connection:
        cursor = connection.execute(
            "UPDATE documents SET parse_status = 'failed', "
            "error_message = 'Server restarted while task was running', "
            "updated_at = datetime('now') "
            "WHERE parse_status = 'running'"
        )
        parse_failed = cursor.rowcount
        cursor = connection.execute(
            "UPDATE documents SET index_status = 'failed', "
            "error_message = 'Server restarted while task was running', "
            "updated_at = datetime('now') "
            "WHERE index_status = 'running'"
        )
        index_failed = cursor.rowcount
    if parse_failed or index_failed:
        _logger.warning(
            "Recovered stuck documents: %d parse, %d index marked as failed",
            parse_failed,
            index_failed,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    _logger.info("Starting Knowledge Agent backend")
    init_db()
    _recover_stuck_documents()
    yield
    _logger.info("Shutting down Knowledge Agent backend")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    # CORS — 生产环境应限制 origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 限制上传请求体大小
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def enforce_max_upload(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_upload_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large. Maximum is {settings.max_upload_bytes} bytes."
                },
            )
        return await call_next(request)

    app.include_router(knowledge_bases_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "Knowledge Agent backend is running"}

    @app.get("/health")
    def health() -> dict:
        checks: dict[str, str] = {}

        # 数据库
        try:
            with connection_scope() as conn:
                conn.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        # ChromaDB
        try:
            from .vector_store import ChromaVectorStore

            store = ChromaVectorStore()
            store.client.list_collections()
            checks["chromadb"] = "ok"
        except Exception as exc:
            checks["chromadb"] = f"error: {exc}"

        all_ok = all(v == "ok" for v in checks.values())
        return {"status": "ok" if all_ok else "degraded", "checks": checks}

    return app


app = create_app()

