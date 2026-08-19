"""
veloctra_orchestrator/scheduler.py
==================================
Lightweight in-process asynchronous Pipeline Scheduler supporting interval & cron schedules.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScheduledJob:
    def __init__(
        self,
        schedule_id: str,
        pipeline_id: str,
        tenant_id: str,
        interval_seconds: int,
        runner_fn: Callable[[str, str], Coroutine[Any, Any, Any]],
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ):
        self.schedule_id = schedule_id
        self.pipeline_id = pipeline_id
        self.tenant_id = tenant_id
        self.interval_seconds = max(1, interval_seconds)
        self.runner_fn = runner_fn
        self.config = config or {}
        self.enabled = enabled
        self.last_run_time: Optional[float] = None
        self.next_run_time: float = time.time() + self.interval_seconds
        self.run_count: int = 0
        self.last_status: str = "PENDING"
        self.last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "pipeline_id": self.pipeline_id,
            "tenant_id": self.tenant_id,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run_time": self.last_run_time,
            "next_run_time": self.next_run_time,
            "run_count": self.run_count,
            "last_status": self.last_status,
            "last_error": self.last_error,
        }


class PipelineScheduler:
    """
    Lightweight background job runner that ticks periodically and dispatches
    scheduled pipeline triggers asynchronously.
    """

    def __init__(self, tick_interval_seconds: float = 1.0):
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._tick_interval = tick_interval_seconds

    def add_schedule(
        self,
        schedule_id: str,
        pipeline_id: str,
        tenant_id: str,
        interval_seconds: int,
        runner_fn: Callable[[str, str], Coroutine[Any, Any, Any]],
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> ScheduledJob:
        job = ScheduledJob(
            schedule_id=schedule_id,
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            interval_seconds=interval_seconds,
            runner_fn=runner_fn,
            config=config,
            enabled=enabled,
        )
        self._jobs[schedule_id] = job
        logger.info("[Scheduler] Registered schedule '%s' for pipeline '%s' (every %ds)", schedule_id, pipeline_id, interval_seconds)
        return job

    def remove_schedule(self, schedule_id: str) -> bool:
        if schedule_id in self._jobs:
            del self._jobs[schedule_id]
            logger.info("[Scheduler] Removed schedule '%s'", schedule_id)
            return True
        return False

    def list_schedules(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        jobs = self._jobs.values()
        if tenant_id:
            jobs = [j for j in jobs if j.tenant_id == tenant_id]
        return [j.to_dict() for j in jobs]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._tick_loop())
        logger.info("[Scheduler] In-process Pipeline Scheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        logger.info("[Scheduler] In-process Pipeline Scheduler stopped")

    async def _tick_loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                for job in list(self._jobs.values()):
                    if job.enabled and now >= job.next_run_time:
                        job.next_run_time = now + job.interval_seconds
                        asyncio.create_task(self._execute_scheduled_job(job))
            except Exception as e:
                logger.error("[Scheduler] Error in scheduler tick: %s", e)

            await asyncio.sleep(self._tick_interval)

    async def _execute_scheduled_job(self, job: ScheduledJob) -> None:
        logger.info("[Scheduler] Triggering scheduled job '%s' (pipeline: %s)", job.schedule_id, job.pipeline_id)
        job.last_run_time = time.time()
        job.run_count += 1
        try:
            res = await job.runner_fn(job.pipeline_id, job.tenant_id)
            job.last_status = "SUCCESS"
            job.last_error = None
        except Exception as exc:
            job.last_status = "FAILED"
            job.last_error = str(exc)
            logger.error("[Scheduler] Scheduled execution '%s' failed: %s", job.schedule_id, exc)
