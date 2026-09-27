"""Per-identity rate limiting for the API gateway."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.core.session_memory import get_redis

logger = get_logger("arcas.ratelimit")


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded.")


class RateLimiter:
    """Fixed-window request limiter."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._lock = threading.Lock()
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def _check_redis(self, identity: str) -> bool:
        client = get_redis()
        if client is None:
            return False
        try:
            window_id = int(time.time() // self.window)
            key = f"arcas:ratelimit:{identity}:{window_id}"
            count = client.incr(key)
            if count == 1:
                client.expire(key, self.window)
            if count > self.limit:
                raise RateLimitExceeded(retry_after=self.window)
            return True
        except RateLimitExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis rate-limit path failed, using memory: %s", exc)
            return False

    def check(self, identity: str) -> None:
        """Raise RateLimitExceeded if identity is over its quota."""
        if self.limit <= 0:
            return

        if self._check_redis(identity):
            return

        now = time.time()
        with self._lock:
            bucket = self._hits[identity]
            cutoff = now - self.window
            bucket[:] = [ts for ts in bucket if ts > cutoff]
            if len(bucket) >= self.limit:
                oldest = bucket[0]
                raise RateLimitExceeded(
                    retry_after=int(self.window - (now - oldest)) + 1
                )
            bucket.append(now)


rate_limiter = RateLimiter(
    limit=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


def client_identity(request) -> Tuple[str, str]:
    """Return (identity, kind) for a Starlette/FastAPI request."""
    user = getattr(request.state, "user", None)
    if user:
        return str(user), "user"
    client = request.client.host if request.client else "anonymous"
    return client, "ip"
