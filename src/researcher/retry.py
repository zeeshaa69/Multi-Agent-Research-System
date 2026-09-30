"""Retry with exponential backoff for transient failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .config import RetryConfig
from .errors import TransientError

T = TypeVar("T")
Sleep = Callable[[float], Awaitable[None]]


def backoff_delay(cfg: RetryConfig, attempt: int) -> float:
    """Delay before the retry that follows failed attempt number ``attempt`` (1-based)."""
    return min(cfg.max_delay, cfg.base_delay * cfg.factor ** (attempt - 1))


async def with_retry(
    func: Callable[[], Awaitable[T]],
    cfg: RetryConfig,
    *,
    sleep: Sleep = asyncio.sleep,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> tuple[T, int]:
    """Run ``func``, retrying only :class:`TransientError`. Returns (result, attempts)."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return await func(), attempt
        except TransientError as exc:
            if attempt >= cfg.max_attempts:
                raise
            delay = backoff_delay(cfg, attempt)
            if on_retry:
                on_retry(attempt, exc, delay)
            await sleep(delay)
