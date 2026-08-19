"""
veloctra_resilience/circuit_breaker.py
=======================================
Async CircuitBreaker pattern with CLOSED -> OPEN -> HALF_OPEN automaton.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set, Tuple, Type

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    def __init__(self, breaker_name: str, retry_after: float):
        super().__init__(f"Circuit breaker '{breaker_name}' is OPEN. Retry available in {retry_after:.1f}s")
        self.breaker_name = breaker_name
        self.retry_after = retry_after


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        broadcaster: Optional[Callable] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.expected_exceptions = expected_exceptions
        self._broadcaster = broadcaster

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def _check_state(self) -> None:
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - (self._last_failure_time or 0)
            if elapsed >= self.cooldown_seconds:
                await self._transition_to(CircuitState.HALF_OPEN)
            else:
                retry_after = self.cooldown_seconds - elapsed
                raise CircuitOpenError(self.name, retry_after)

    async def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        logger.info("[CircuitBreaker:%s] State changed: %s → %s", self.name, old_state.value, new_state.value)
        if self._broadcaster:
            try:
                res = self._broadcaster({
                    "event": "circuit_breaker",
                    "name": self.name,
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                    "failure_count": self._failure_count,
                    "timestamp": time.time(),
                })
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    async def record_success(self) -> None:
        async with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                await self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0

    async def record_failure(self, exc: Exception) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            logger.warning(
                "[CircuitBreaker:%s] Failure #%d/%d: %s",
                self.name, self._failure_count, self.failure_threshold, exc,
            )
            if self._failure_count >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
                await self._transition_to(CircuitState.OPEN)

    async def __aenter__(self) -> "CircuitBreaker":
        async with self._lock:
            await self._check_state()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_val is None:
            await self.record_success()
        elif isinstance(exc_val, self.expected_exceptions):
            await self.record_failure(exc_val)
        return False

    def __call__(self, fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with self:
                return await fn(*args, **kwargs)
        return wrapper

    async def reset(self) -> None:
        async with self._lock:
            self._failure_count = 0
            await self._transition_to(CircuitState.CLOSED)

    async def trip(self) -> None:
        async with self._lock:
            self._last_failure_time = time.time()
            await self._transition_to(CircuitState.OPEN)


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        broadcaster: Optional[Callable] = None,
    ) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
                broadcaster=broadcaster,
            )
        return self._breakers[name]

    def all_statuses(self) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        result = {}
        for name, cb in self._breakers.items():
            retry_after = 0.0
            if cb.state == CircuitState.OPEN and cb._last_failure_time:
                elapsed = now - cb._last_failure_time
                retry_after = max(0.0, cb.cooldown_seconds - elapsed)
            result[name] = {
                "name": name,
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "retry_after_seconds": round(retry_after, 1),
            }
        return result


circuit_registry = CircuitBreakerRegistry()
