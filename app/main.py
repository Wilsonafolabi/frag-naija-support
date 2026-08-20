import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.config import get_settings
from app.log import configure_logging
from app.ai.base import LLMProviderError

from app.rag.embeddings import LocalEmbedder
from app.rag.vector_store import QdrantStore
from app.rag.reranker import LocalReranker

from app.db.session import engine
from app.models.chat import Base
from app.models.ticket import SupportTicket
from app.knowledge.models import IngestionRun, KnowledgeSource  # Stage 26: create knowledge tables

from app.security.rate_limit import limiter
from app.observability.langfuse_tracer import get_langfuse_client

logger = structlog.get_logger(__name__)


class RequestSizeLimitMiddleware:
    """Rejects HTTP bodies larger than max_size (default 1MB)."""

    def __init__(self, app, max_size: int = 1024 * 1024):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        total_size = 0

        async def wrapped_receive():
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                total_size += len(body)
                if total_size > self.max_size:
                    logger.warning("request_size_exceeded", size=total_size, max=self.max_size)
                    raise HTTPException(status_code=413, detail="Request body too large")
            return message

        await self.app(scope, wrapped_receive, send)


class SecurityHeadersMiddleware:
    """Adds security headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
                ]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, wrapped_send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings

    logger.info("initializing_rag_components")
    app.state.embedder = LocalEmbedder(settings.embedding_model)
    app.state.qdrant_store = QdrantStore(settings)
    await app.state.qdrant_store.ensure_collection(vector_size=app.state.embedder.dimension)

    app.state.reranker = None
    if settings.reranker_enabled:
        logger.info("initializing_reranker", model=settings.reranker_model)
        app.state.reranker = LocalReranker(settings.reranker_model)
    else:
        logger.info("reranker_disabled")

    logger.info("initializing_database_tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info(
        "application_startup",
        service=settings.app_name,
        environment=settings.environment,
        groq_configured=settings.groq_configured,
        reranker_enabled=settings.reranker_enabled,
        langfuse_enabled=settings.langfuse_enabled,
    )

    yield

    logger.info("application_shutdown", service=settings.app_name)
    if app.state.langfuse_client:
        app.state.langfuse_client.flush()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=False,  # never enable debug in production
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.langfuse_client = get_langfuse_client(settings)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS - restricted in production
    cors_origins = settings.cors_origin_list if settings.environment == "production" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False if settings.is_production else True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Request size limit (1MB)
    app.add_middleware(RequestSizeLimitMiddleware, max_size=1024 * 1024)

    # Trusted host validation (production only)
    if settings.is_production and settings.allowed_hosts_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info("request_completed", duration_ms=duration_ms)

        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(chat_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [{"loc": err.get("loc"), "msg": err.get("msg"), "type": err.get("type")} for err in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})

    @app.exception_handler(LLMProviderError)
    async def llm_provider_error_handler(request: Request, exc: LLMProviderError):
        logger.error("llm_provider_error", error=str(exc))
        return JSONResponse(status_code=503, content={"detail": "AI service unavailable."})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        logger.error("unhandled_exception", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()