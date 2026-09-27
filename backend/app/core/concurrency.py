"""Process-wide concurrency primitives for the orchestration layer."""

import asyncio

from app.core.config import settings

# Bounds the number of concurrent LLM gateway calls.
llm_semaphore = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENCY))
