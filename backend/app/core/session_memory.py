"""Session memory and cache."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.session")


# Optional Redis client (lazily initialised, cached)

_redis_client = None
_redis_initialised = False
_redis_lock = threading.Lock()


def get_redis():
    """Return a connected Redis client or None (cached after first attempt)."""
    global _redis_client, _redis_initialised
    if _redis_initialised:
        return _redis_client

    with _redis_lock:
        if _redis_initialised:
            return _redis_client
        _redis_initialised = True

        if not settings.REDIS_URL:
            _redis_client = None
            return None

        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(
                settings.REDIS_URL, decode_responses=True
            )
            client.ping()
            _redis_client = client
            logger.info("Connected to Redis for session memory.")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Redis unavailable (%s); using in-process session store.", exc
            )
            _redis_client = None

    return _redis_client


# In-process TTL fallback

class _MemoryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._expires: Dict[str, float] = {}

    def _purge(self):
        now = time.time()
        expired = [k for k, exp in self._expires.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)
            self._expires.pop(k, None)

    def set(self, key: str, value: str, ttl: int):
        with self._lock:
            self._purge()
            self._data[key] = value
            self._expires[key] = time.time() + ttl

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            self._purge()
            return self._data.get(key)

    def append(self, key: str, value: str, ttl: int):
        with self._lock:
            self._purge()
            lst = json.loads(self._data.get(key, "[]"))
            lst.append(value)
            self._data[key] = json.dumps(lst)
            self._expires[key] = time.time() + ttl

    def list(self, key: str) -> List[str]:
        with self._lock:
            self._purge()
            return json.loads(self._data.get(key, "[]"))


_memory_store = _MemoryStore()


# Public session API

class SessionMemory:
    """Short-term multi-turn memory for a conversation/session id."""

    @staticmethod
    def _key(session_id: str) -> str:
        return f"arcas:session:{session_id}"

    @staticmethod
    def record_turn(session_id: str, turn: Dict[str, Any]) -> None:
        """Append a turn (request/response summary) to a session's history."""
        payload = json.dumps(turn)
        client = get_redis()
        if client is not None:
            try:
                key = SessionMemory._key(session_id)
                client.rpush(key, payload)
                client.expire(key, settings.SESSION_TTL_SECONDS)
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis record_turn failed: %s", exc)
        _memory_store.append(
            SessionMemory._key(session_id),
            payload,
            settings.SESSION_TTL_SECONDS,
        )

    @staticmethod
    def history(session_id: str) -> List[Dict[str, Any]]:
        client = get_redis()
        if client is not None:
            try:
                key = SessionMemory._key(session_id)
                return [json.loads(item) for item in client.lrange(key, 0, -1)]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis history failed: %s", exc)
        return [
            json.loads(item)
            for item in _memory_store.list(SessionMemory._key(session_id))
        ]


class Cache:
    """Generic small TTL cache (used e.g. for LLM response memoisation)."""

    @staticmethod
    def get(key: str) -> Optional[str]:
        client = get_redis()
        if client is not None:
            try:
                return client.get(f"arcas:cache:{key}")
            except Exception:  # noqa: BLE001
                pass
        return _memory_store.get(f"arcas:cache:{key}")

    @staticmethod
    def set(key: str, value: str, ttl: int = 300) -> None:
        client = get_redis()
        if client is not None:
            try:
                client.set(f"arcas:cache:{key}", value, ex=ttl)
                return
            except Exception:  # noqa: BLE001
                pass
        _memory_store.set(f"arcas:cache:{key}", value, ttl)
