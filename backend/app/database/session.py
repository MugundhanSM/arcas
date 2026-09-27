"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.database")

# Local file used when the configured database driver is unavailable.
FALLBACK_DATABASE_URL = "sqlite:///./arcas_fallback.db"

_using_fallback = False
_fallback_reason = ""


def _make_engine(url: str):
    kwargs: dict = {"echo": settings.DEBUG, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping", None)
    return create_engine(url, **kwargs)


try:
    engine = _make_engine(settings.DATABASE_URL)
except Exception as exc:  # noqa: BLE001 - missing driver, bad URL, etc.
    _using_fallback = True
    _fallback_reason = f"{exc.__class__.__name__}: {exc}"
    logger.warning(
        "Could not initialise the configured database (%s). Falling back to "
        "%s. Persistence is LOCAL ONLY - install the driver and set "
        "DATABASE_URL for the real deployment.",
        _fallback_reason,
        FALLBACK_DATABASE_URL,
    )
    engine = _make_engine(FALLBACK_DATABASE_URL)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def engine_status() -> dict:
    """Report which backend is actually in use (surfaced on /health)."""
    return {
        "dialect": engine.dialect.name,
        "using_fallback": _using_fallback,
        "fallback_reason": _fallback_reason or None,
    }
