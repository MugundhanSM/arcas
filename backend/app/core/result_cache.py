"""Result cache for the deterministic tools and the LLM agents."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.session_memory import Cache

logger = get_logger("arcas.cache")


def _key(agent_name: str, source_code: str, language: str, extra: str) -> str:
    digest = hashlib.sha256()
    for part in (agent_name, language or "", extra or "", source_code or ""):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\x00")
    return f"{agent_name}:{digest.hexdigest()}"


class ResultCache:
    """Hash-keyed memoisation of tool / agent results."""

    @staticmethod
    def get_text(
        agent_name: str,
        source_code: str,
        language: str,
        extra: str = "",
    ) -> Optional[str]:
        if not settings.ENABLE_RESULT_CACHE:
            return None
        value = Cache.get(_key(agent_name, source_code, language, extra))
        if value is not None:
            logger.debug("Cache hit (%s)", agent_name)
        return value

    @staticmethod
    def set_text(
        agent_name: str,
        source_code: str,
        language: str,
        value: str,
        extra: str = "",
    ) -> None:
        if not settings.ENABLE_RESULT_CACHE:
            return
        Cache.set(
            _key(agent_name, source_code, language, extra),
            value,
            ttl=settings.RESULT_CACHE_TTL_SECONDS,
        )

    @staticmethod
    def get_json(
        agent_name: str,
        source_code: str,
        language: str,
        extra: str = "",
    ) -> Optional[Any]:
        raw = ResultCache.get_text(agent_name, source_code, language, extra)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def set_json(
        agent_name: str,
        source_code: str,
        language: str,
        value: Any,
        extra: str = "",
    ) -> None:
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError):
            return
        ResultCache.set_text(
            agent_name, source_code, language, serialized, extra
        )
