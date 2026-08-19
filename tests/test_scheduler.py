"""
tests/test_scheduler.py
=======================
Unit tests for in-process lightweight PipelineScheduler.
"""

import asyncio
import pytest
from veloctra_orchestrator.scheduler import PipelineScheduler


@pytest.mark.asyncio
async def test_scheduler_add_and_execute_job():
    scheduler = PipelineScheduler(tick_interval_seconds=0.05)

    executed = []

    async def mock_runner(pipeline_id: str, tenant_id: str):
        executed.append((pipeline_id, tenant_id))
        return 100

    job = scheduler.add_schedule(
        schedule_id="sched_1",
        pipeline_id="claims_sync",
        tenant_id="tenant_alpha",
        interval_seconds=1,
        runner_fn=mock_runner,
    )

    # Force next_run_time to now so it triggers on first tick
    job.next_run_time = 0

    await scheduler.start()
    await asyncio.sleep(0.15)
    await scheduler.stop()

    assert len(executed) >= 1
    assert executed[0] == ("claims_sync", "tenant_alpha")
    assert job.last_status == "SUCCESS"
    assert job.run_count >= 1

    schedules = scheduler.list_schedules("tenant_alpha")
    assert len(schedules) == 1
    assert schedules[0]["pipeline_id"] == "claims_sync"

    removed = scheduler.remove_schedule("sched_1")
    assert removed is True
    assert len(scheduler.list_schedules()) == 0
