"""
tests/test_retry.py
====================
Unit tests for the async_retry decorator and RetryContext.
"""

import asyncio
import pytest

from veloctra_resilience.retry import (
    async_retry,
    MaxRetriesExceededError,
    RetryContext,
)



@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    call_count = 0

    @async_retry(max_attempts=3)
    async def fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await fn()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_failures():
    call_count = 0

    @async_retry(max_attempts=4, initial_backoff=0.01, max_backoff=0.1)
    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "recovered"

    result = await fn()
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_raises_after_all_attempts_exhausted():
    call_count = 0

    @async_retry(max_attempts=3, initial_backoff=0.01, max_backoff=0.05)
    async def fn():
        nonlocal call_count
        call_count += 1
        raise IOError("always fails")

    with pytest.raises(MaxRetriesExceededError) as exc_info:
        await fn()

    assert call_count == 3
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, IOError)


@pytest.mark.asyncio
async def test_retry_only_on_retriable_exceptions():
    """IOError IS in the retriable list — it should be retried up to max_attempts."""
    call_count = 0

    @async_retry(
        max_attempts=3,
        initial_backoff=0.01,
        retriable_exceptions=(IOError,),
    )
    async def fn():
        nonlocal call_count
        call_count += 1
        raise IOError("retriable failure")

    with pytest.raises(MaxRetriesExceededError):
        await fn()

    assert call_count == 3  # all 3 attempts used


@pytest.mark.asyncio
async def test_non_retriable_exception_not_caught():
    """KeyError is NOT in retriable list — decorator should re-raise immediately."""
    call_count = 0

    @async_retry(
        max_attempts=5,
        initial_backoff=0.01,
        retriable_exceptions=(IOError,),  # KeyError not listed
    )
    async def fn():
        nonlocal call_count
        call_count += 1
        raise KeyError("not retriable")

    with pytest.raises(KeyError):
        await fn()

    assert call_count == 1  # no retries — first attempt propagates immediately



@pytest.mark.asyncio
async def test_retry_non_retriable_exception_propagates():
    @async_retry(
        max_attempts=5,
        initial_backoff=0.01,
        retriable_exceptions=(IOError,),  # only IOError is retriable
    )
    async def fn():
        raise KeyboardInterrupt("not retriable")

    with pytest.raises(KeyboardInterrupt):
        await fn()


@pytest.mark.asyncio
async def test_on_retry_callback_called():
    retry_calls = []

    async def on_retry(attempt, exc, delay):
        retry_calls.append((attempt, type(exc).__name__))

    @async_retry(max_attempts=3, initial_backoff=0.01, on_retry=on_retry)
    async def fn():
        raise ValueError("fail")

    with pytest.raises(MaxRetriesExceededError):
        await fn()

    assert len(retry_calls) == 2  # called before each of the 2 retries


@pytest.mark.asyncio
async def test_retry_context_succeed():
    result = None
    ctx = RetryContext(max_attempts=5, initial_backoff=0.01)
    async for attempt in ctx:
        if attempt == 2:
            result = "done"
            ctx.succeed()
            break
        await ctx.fail(ValueError("not yet"))

    assert result == "done"


@pytest.mark.asyncio
async def test_retry_context_exhausted():
    ctx = RetryContext(max_attempts=3, initial_backoff=0.01)
    with pytest.raises(MaxRetriesExceededError):
        async for _ in ctx:
            await ctx.fail(RuntimeError("always"))
