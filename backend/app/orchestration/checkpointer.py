"""LangGraph checkpointing."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.orchestration.checkpointer")

_checkpointer: Optional[Any] = None
_backend: str = "none"
_reason: str = ""


def _try_redis() -> Optional[Any]:
    """Redis-backed saver - the documented production backend."""
    if not settings.REDIS_URL:
        return None
    try:
        from langgraph.checkpoint.redis import RedisSaver  # type: ignore

        saver = RedisSaver.from_conn_string(settings.REDIS_URL)
        if hasattr(saver, "__enter__"):
            saver = saver.__enter__()
        if hasattr(saver, "setup"):
            saver.setup()
        return saver
    except ImportError:
        logger.info(
            "langgraph-checkpoint-redis is not installed; trying SQLite."
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis checkpointer unavailable (%s).", exc)
    return None


def _try_sqlite() -> Optional[Any]:
    return None


def _try_memory() -> Optional[Any]:
    try:
        from langgraph.checkpoint.memory import MemorySaver  # type: ignore

        return MemorySaver()
    except Exception as exc:  # noqa: BLE001
        logger.warning("In-memory checkpointer unavailable (%s).", exc)
    return None


def get_checkpointer() -> Optional[Any]:
    """Return the process-wide checkpointer, building it on first use."""
    global _checkpointer, _backend, _reason

    if _checkpointer is not None or _backend != "none":
        return _checkpointer

    if not settings.ENABLE_CHECKPOINTING:
        _backend = "disabled"
        _reason = "ENABLE_CHECKPOINTING is false"
        logger.info("Graph checkpointing disabled by configuration.")
        return None

    for name, factory in (
        ("redis", _try_redis),
        ("sqlite", _try_sqlite),
        ("memory", _try_memory),
    ):
        saver = factory()
        if saver is not None:
            _checkpointer = saver
            _backend = name
            if name != "redis":
                _reason = (
                    "Redis is the documented durable backend. In-memory "
                    "checkpoints are per-process and lost on restart - fine "
                    "for development, not for a multi-worker deployment. Set "
                    "REDIS_URL and install langgraph-checkpoint-redis."
                )
            logger.info("LangGraph checkpointer backend: %s.", name)
            return saver

    _backend = "none"
    _reason = "no checkpointer backend could be constructed"
    logger.warning("No LangGraph checkpointer available; graph is stateless.")
    return None


def checkpointer_status() -> Dict[str, Any]:
    """Report the active backend - surfaced on /health."""
    get_checkpointer()
    return {
        "enabled": bool(settings.ENABLE_CHECKPOINTING),
        "backend": _backend,
        "shared_across_processes": _backend == "redis",
        "survives_restart": _backend in ("redis", "sqlite"),
        "note": _reason or None,
    }


def thread_config(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Build the LangGraph config that binds an invocation to a session."""
    return {
        "configurable": {
            "thread_id": str(session_id) if session_id else f"ephemeral-{uuid.uuid4()}"
        }
    }


def reset() -> None:
    """Drop the cached checkpointer (used by tests)."""
    global _checkpointer, _backend, _reason
    _checkpointer = None
    _backend = "none"
    _reason = ""
