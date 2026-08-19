"""
tests/test_circuit_breaker.py
==============================
Unit tests for the async CircuitBreaker.
"""

import asyncio
import pytest
import pytest_asyncio

from veloctra_resilience.circuit_breaker import (
    CircuitBreaker, CircuitState, CircuitOpenError, CircuitBreakerRegistry
)



@pytest.fixture
def cb():
    return CircuitBreaker("test-cb", failure_threshold=3, cooldown_seconds=0.1)


@pytest.mark.asyncio
async def test_initial_state_is_closed(cb):
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_trips_after_threshold_failures(cb):
    for _ in range(3):
        try:
            async with cb:
                raise ValueError("test failure")
        except ValueError:
            pass
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_raises_circuit_open_error(cb):
    # Trip the breaker
    for _ in range(3):
        try:
            async with cb:
                raise ValueError("trip")
        except ValueError:
            pass
    # Now any call should raise CircuitOpenError
    with pytest.raises(CircuitOpenError):
        async with cb:
            pass


@pytest.mark.asyncio
async def test_cooldown_transitions_to_half_open(cb):
    for _ in range(3):
        try:
            async with cb:
                raise ValueError("trip")
        except ValueError:
            pass
    assert cb.state == CircuitState.OPEN
    await asyncio.sleep(0.15)  # cooldown = 0.1s
    # Next call should be allowed (HALF_OPEN probe)
    async with cb:
        pass  # success
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_failure_reopens(cb):
    for _ in range(3):
        try:
            async with cb:
                raise ValueError("trip")
        except ValueError:
            pass
    await asyncio.sleep(0.15)
    try:
        async with cb:
            raise ValueError("probe failure")
    except ValueError:
        pass
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_success_resets_failure_count(cb):
    # One failure then one success
    try:
        async with cb:
            raise ValueError("one failure")
    except ValueError:
        pass
    async with cb:
        pass  # success
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_manual_reset(cb):
    for _ in range(3):
        try:
            async with cb:
                raise ValueError("trip")
        except ValueError:
            pass
    assert cb.state == CircuitState.OPEN
    await cb.reset()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_manual_trip(cb):
    await cb.trip()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_decorator_usage(cb):
    call_count = 0

    @cb
    async def risky():
        nonlocal call_count
        call_count += 1
        raise IOError("boom")

    for _ in range(3):
        try:
            await risky()
        except IOError:
            pass

    assert cb.state == CircuitState.OPEN
    assert call_count == 3


@pytest.mark.asyncio
async def test_registry_get_or_create():
    registry = CircuitBreakerRegistry()
    cb1 = registry.get_or_create("db-conn", failure_threshold=5)
    cb2 = registry.get_or_create("db-conn")
    assert cb1 is cb2  # same instance

    statuses = registry.all_statuses()
    assert "db-conn" in statuses
    assert statuses["db-conn"]["state"] == CircuitState.CLOSED.value
