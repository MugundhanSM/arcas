from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import router as auth_router
from app.api.v1.report import router as report_router
from app.api.v1.review import router as review_router
from app.api.v1.trace import router as trace_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.telemetry import setup_telemetry, start_span, telemetry_status
from app.core.trace_store import TraceStore

setup_logging()
logger = get_logger("arcas.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise resources on startup."""
    logger.info(
        "Starting %s v%s", settings.APP_NAME, settings.APP_VERSION
    )

    try:
        from app.database.migrations import run_migrations
        from app.database.models import Base
        from app.database.session import engine

        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified / created.")

        run_migrations(engine)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not initialise database on startup: %s", exc
        )

    # Layer 9 observability.
    if setup_telemetry(app):
        logger.info("OpenTelemetry tracing active.")

    try:
        from app.tools.semgrep_tool import warm_registry_probe

        warm_registry_probe()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Semgrep probe failed at startup: %s", exc)

    if not settings.llm_configured:
        logger.warning(
            "LLM provider is not configured. Refactor recommendations "
            "will fall back to a deterministic summary."
        )

    yield

    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Open a trace for every request and propagate its id to the client."""
    inbound = request.headers.get("X-Trace-Id")
    trace_id = TraceStore.start_trace(inbound if inbound else None)

    with start_span(
        f"http.{request.method} {request.url.path}",
        layer=2,
        method=request.method,
        path=request.url.path,
    ):
        response = await call_next(request)

    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
):
    """Return a structured error instead of leaking stack traces."""
    logger.exception(
        "Unhandled error processing %s %s", request.method, request.url
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal error occurred while processing "
            "the request.",
            "error_type": exc.__class__.__name__,
        },
    )


@app.get("/", tags=["Health"])
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    from app.core.guardrails import InputGuardrails
    from app.database.session import engine_status
    from app.orchestration.checkpointer import (
        checkpointer_status as _checkpointer_status,
    )
    from app.tools.retriever_tool import RetrieverTool
    from app.tools.treesitter_tool import TreeSitterTool

    return {
        "status": "healthy",
        "llm_configured": settings.llm_configured,
        "auth_required": settings.AUTH_REQUIRED,
        "layers": {
            "L3_input_guardrails": InputGuardrails.capabilities(),
            "L6_tools": TreeSitterTool.capabilities(),
            "L7_knowledge": RetrieverTool.stats(),
            "L8_output_guardrails": {
                "selfcheck_enabled": settings.ENABLE_SELFCHECK,
                "selfcheck_samples": settings.SELFCHECK_SAMPLES or 3,
            },
            "L4_orchestration": _checkpointer_status(),
            "L9_persistence": engine_status(),
            "L9_observability": telemetry_status(),
        },
    }


app.include_router(
    auth_router,
    prefix=settings.API_PREFIX,
    tags=["Authentication"]
)

app.include_router(
    review_router,
    prefix=settings.API_PREFIX,
    tags=["Review"]
)

app.include_router(
    report_router,
    prefix=settings.API_PREFIX,
    tags=["Report"]
)

app.include_router(
    trace_router,
    prefix=settings.API_PREFIX,
)
