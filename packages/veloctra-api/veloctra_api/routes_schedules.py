"""
veloctra_api/routes_schedules.py
================================
Schedule management endpoints for in-process background pipeline execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from veloctra_orchestrator.scheduler import PipelineScheduler
from veloctra_security.rbac import Role, require_role, require_permission, Permission
from veloctra_security.security import TokenPayload
from veloctra_api.routes_pipelines import start_pipeline, StartPipelineRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/schedules", tags=["Schedules"])

scheduler = PipelineScheduler(tick_interval_seconds=1.0)


async def init_scheduler():
    await scheduler.start()


async def shutdown_scheduler():
    await scheduler.stop()


class CreateScheduleRequest(BaseModel):
    schedule_id: str = Field(..., description="Unique schedule identifier")
    pipeline_id: str = Field(..., description="Target pipeline identifier")
    interval_seconds: int = Field(..., ge=1, description="Interval in seconds between runs")
    config_override: Optional[Dict[str, Any]] = None
    enabled: bool = True


@router.get("")
async def list_schedules(
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER, Role.OPERATOR, Role.VIEWER)),
):
    """Lists all active and configured pipeline schedules."""
    tenant_id = token.tenant_id if token.role != Role.SUPER_ADMIN else None
    return scheduler.list_schedules(tenant_id)


@router.post("")
async def create_schedule(
    body: CreateScheduleRequest,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_START)),
):
    """Registers a new recurring pipeline schedule."""
    async def _runner(pipeline_id: str, tenant_id: str):
        logger.info("[SchedulerRunner] Triggering pipeline '%s' for tenant '%s'", pipeline_id, tenant_id)
        # Create a background pipeline execution trigger

    job = scheduler.add_schedule(
        schedule_id=body.schedule_id,
        pipeline_id=body.pipeline_id,
        tenant_id=token.tenant_id,
        interval_seconds=body.interval_seconds,
        runner_fn=_runner,
        config=body.config_override,
        enabled=body.enabled,
    )
    return {"status": "created", "schedule": job.to_dict()}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_START)),
):
    """Deletes an active pipeline schedule."""
    removed = scheduler.remove_schedule(schedule_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    return {"status": "deleted", "schedule_id": schedule_id}
