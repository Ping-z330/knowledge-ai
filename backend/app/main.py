import logging
import os
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import connection_scope, init_db
from .logging_config import request_id_var, setup_logging
from .routers import documents, history, knowledge_bases, qa
from .dependencies import get_tq
from .task_queue import TASK_INDEX, TASK_PARSE

_logger = logging.getLogger(__name__)


def _rebuild_all_keyword_indexes() -> None:
    """重建所有知识库的 BM25 关键词索引，优先从磁盘加载。"""
    try:
        from .dependencies import get_kw_engine

        engine = get_kw_engine()
        if engine.load_from_disk():
            _logger.info("Keyword indexes restored from disk, skipping full rebuild")
            return

        from .database import connect
        from .services.indexing import rebuild_keyword_index

        connection = connect()
        try:
            kb_rows = connection.execute(
                "SELECT id FROM knowledge_bases"
            ).fetchall()
            chunk_rows = connection.execute(
                "SELECT knowledge_base_id FROM chunks GROUP BY knowledge_base_id"
            ).fetchall()
            kb_ids = {row["id"] for row in kb_rows}
            indexed_ids = {row["knowledge_base_id"] for row in chunk_rows}

            for kb_id in indexed_ids & kb_ids:
                db_conn = connect()
                try:
                    chunk_dicts = db_conn.execute(
                        """
                        SELECT id, knowledge_base_id, document_id, chunk_index,
                               text, source_label, page_number, section_title
                        FROM chunks WHERE knowledge_base_id = ?
                        ORDER BY chunk_index ASC
                        """,
                        (kb_id,),
                    ).fetchall()
                    if chunk_dicts:
                        rebuild_keyword_index(
                            knowledge_base_id=kb_id,
                            chunks=[dict(r) for r in chunk_dicts],
                            debounce=False,
                        )
                finally:
                    db_conn.close()
        finally:
            connection.close()
    except Exception:
        _logger.warning("Failed to rebuild keyword indexes on startup", exc_info=True)


def _recover_stuck_documents() -> None:
    """将服务重启后卡在 running 状态的文档和 pending/running 任务标记为 failed。"""
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
        cursor = connection.execute(
            "UPDATE tasks SET status = 'failed', "
            "error_message = 'Server restarted while task was running', "
            "updated_at = datetime('now') "
            "WHERE status IN ('pending', 'running')"
        )
        task_failed = cursor.rowcount
    if parse_failed or index_failed or task_failed:
        _logger.warning(
            "Recovered stuck documents: %d parse, %d index, %d tasks marked as failed",
            parse_failed,
            index_failed,
            task_failed,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(json_format=settings.log_json)
    _logger.info("Starting Knowledge Agent backend")
    init_db()
    _recover_stuck_documents()

    # 设置关键词索引持久化目录
    from .dependencies import get_kw_engine
    from .config import BACKEND_DIR

    get_kw_engine().set_persist_dir(BACKEND_DIR / "data")
    _rebuild_all_keyword_indexes()

    # 注册任务队列处理器并启动 worker
    from .routers.documents import (
        _run_index_document_task,
        _run_parse_document_task,
    )

    tq = get_tq()
    tq.register_handler(TASK_PARSE, _run_parse_document_task)
    tq.register_handler(TASK_INDEX, _run_index_document_task)
    tq.start()

    yield

    tq.stop()
    _logger.info("Shutting down Knowledge Agent backend")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    # CORS — allow_origins 通过 CORS_ORIGINS 环境变量配置（逗号分隔），默认 "*"
    cors_origins = settings.cors_origins
    if cors_origins == "*":
        allow_origins = ["*"]
    else:
        allow_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting — 默认 60 req/min per IP
    # 使用纯 ASGI middleware 避免 BaseHTTPMiddleware 与 StreamingResponse 的兼容问题
    from .rate_limit import RateLimiter

    rate_limit_req = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    rate_limit_win = float(os.getenv("RATE_LIMIT_WINDOW", "60"))
    _limiter = RateLimiter(max_requests=rate_limit_req, window_seconds=rate_limit_win)
    _skip_paths = {"/health", "/"}

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path in _skip_paths:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        if not _limiter.is_allowed(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试。"},
            )
        return await call_next(request)

    # X-Request-ID — 透传客户端传入的，否则生成新的
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    # 限制上传请求体大小
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

    app.include_router(knowledge_bases.router)
    app.include_router(documents.router)
    app.include_router(qa.router)
    app.include_router(history.router)

    from .routers import conversations

    app.include_router(conversations.router)

    # Agentic RAG 端点（可通过 AGENTIC_ENABLED 环境变量关闭）
    if settings.agentic_enabled:
        try:
            from .routers import agentic_qa

            app.include_router(agentic_qa.router)
            _logger.info("Agentic RAG endpoints enabled")
        except ImportError as exc:
            _logger.warning(
                "Agentic RAG endpoints disabled — missing dependencies: %s. "
                "Install with: pip install langgraph langchain-core openai duckduckgo-search",
                exc,
            )

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

        # LLM
        try:
            import httpx
            from .config import get_settings

            settings = get_settings()
            if settings.llm_base_url:
                resp = httpx.get(
                    f"{settings.llm_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"}
                    if settings.llm_api_key
                    else {},
                    timeout=5.0,
                    proxy=None,
                )
                if resp.status_code < 500:
                    checks["llm"] = "ok"
                else:
                    checks["llm"] = f"error: status {resp.status_code}"
            else:
                checks["llm"] = "skipped (not configured)"
        except Exception as exc:
            checks["llm"] = f"error: {exc}"

        all_ok = all(v == "ok" for v in checks.values())
        return {"status": "ok" if all_ok else "degraded", "checks": checks}

    return app


app = create_app()

