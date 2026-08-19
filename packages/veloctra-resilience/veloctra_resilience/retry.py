"""
veloctra_resilience/retry.py
=============================
Exponential backoff with full jitter retry decorator for async functions.
Algorithm (Full Jitter — recommended by AWS):
    sleep = random.uniform(0, min(cap, base * 2 ** attempt))
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class MaxRetriesExceededError(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"Exceeded {attempts} retry attempt(s). Last error: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def _full_jitter(attempt: int, base: float, cap: float) -> float:
    return random.uniform(0, min(cap, base * (2 ** attempt)))


def async_retry(
    max_attempts: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    retriable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc: Optional[Exception] = None

            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except retriable_exceptions as exc:
                    last_exc = exc
                    remaining = max_attempts - attempt - 1

                    if remaining == 0:
                        break

                    delay = _full_jitter(attempt, initial_backoff, max_backoff)
                    logger.warning(
                        "[Retry] %s attempt %d/%d failed: %s. Retrying in %.2fs…",
                        fn.__qualname__, attempt + 1, max_attempts, exc, delay,
                    )

                    if on_retry is not None:
                        try:
                            await on_retry(attempt, exc, delay)
                        except Exception:
                            pass

                    await asyncio.sleep(delay)

            raise MaxRetriesExceededError(max_attempts, last_exc)

        return wrapper
    return decorator


class RetryContext:
    def __init__(
        self,
        max_attempts: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self._max = max_attempts
        self._base = initial_backoff
        self._cap = max_backoff
        self._attempt = 0
        self._succeeded = False

    def __aiter__(self):
        self._attempt = 0
        self._succeeded = False
        return self

    async def __anext__(self) -> int:
        if self._succeeded or self._attempt >= self._max:
            raise StopAsyncIteration
        return self._attempt

    def succeed(self) -> None:
        self._succeeded = True

    async def fail(self, exc: Exception) -> None:
        self._attempt += 1
        if self._attempt >= self._max:
            raise MaxRetriesExceededError(self._max, exc) from exc
        delay = _full_jitter(self._attempt, self._base, self._cap)
        logger.warning(
            "[RetryContext] Attempt %d/%d failed: %s. Retrying in %.2fs…",
            self._attempt, self._max, exc, delay,
        )
        await asyncio.sleep(delay)
