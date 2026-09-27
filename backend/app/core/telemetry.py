"""OpenTelemetry instrumentation."""

from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.telemetry")

_configured = False

try:
    from opentelemetry import trace

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    trace = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False


def setup_telemetry(app: Any = None) -> bool:
    """Configure tracing once."""
    global _configured
    if _configured:
        return True
    if not settings.ENABLE_TELEMETRY:
        logger.info("Telemetry disabled (ENABLE_TELEMETRY=false).")
        return False
    if not _OTEL_AVAILABLE:
        logger.warning(
            "ENABLE_TELEMETRY is true but the 'opentelemetry' packages are "
            "not installed; tracing is inactive. Install requirements-otel.txt."
        )
        return False

    from opentelemetry.sdk.resources import (
        SERVICE_NAME,
        SERVICE_VERSION,
        Resource,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    resource = Resource.create(
        {
            SERVICE_NAME: settings.APP_NAME,
            SERVICE_VERSION: settings.APP_VERSION,
        }
    )
    provider = TracerProvider(resource=resource)

    exporter: Any = None
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
            logger.info("Telemetry exporting to OTLP endpoint %s", endpoint)
        except ImportError:
            logger.warning(
                "OTLP exporter not installed; falling back to console export."
            )
    if exporter is None:
        exporter = ConsoleSpanExporter()
        logger.info("Telemetry exporting spans to the console.")

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if app is not None:
        with contextlib.suppress(ImportError):
            from opentelemetry.instrumentation.fastapi import (
                FastAPIInstrumentor,
            )

            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumented for request tracing.")

    _configured = True
    return True


@contextlib.contextmanager
def start_span(name: str, layer: int = 5, **attributes: Any) -> Iterator[Any]:
    """Open a span around a block of work, on every active backend."""
    from app.core.trace_store import SpanRecorder

    with SpanRecorder(name, layer, **attributes) as recorder:
        if not _OTEL_AVAILABLE:
            yield recorder
            return

        tracer = trace.get_tracer("arcas")
        with tracer.start_as_current_span(name) as span:
            with contextlib.suppress(Exception):
                span.set_attribute("arcas.layer", layer)
            for key, value in attributes.items():
                with contextlib.suppress(Exception):
                    span.set_attribute(key, value)
            yield recorder


def traced_node(name: str, fn: Callable[[Any], Any], layer: int = 5):
    """Wrap a graph node so each agent execution emits its own span."""
    import asyncio
    import functools

    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _async_runner(state: Any) -> Any:
            with start_span(f"agent.{name}", layer=layer):
                return await fn(state)

        _async_runner.__name__ = f"{name}_traced"
        return _async_runner

    @functools.wraps(fn)
    def _runner(state: Any) -> Any:
        with start_span(f"agent.{name}", layer=layer):
            return fn(state)

    _runner.__name__ = f"{name}_traced"
    return _runner


def telemetry_status() -> dict:
    """Report which observability backends are actually active."""
    return {
        "otel_sdk_installed": _OTEL_AVAILABLE,
        "otel_enabled": bool(settings.ENABLE_TELEMETRY),
        "otel_configured": _configured,
        "otel_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT or None,
        "in_process_tracing": True,
    }
