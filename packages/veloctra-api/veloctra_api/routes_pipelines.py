"""
veloctra_api/routes_pipelines.py
================================
Pipeline execution lifecycle, status inspection, and DLQ management endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
import psutil
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from veloctra_api.websocket import manager as ws_manager, telemetry_broadcaster
from veloctra_security.rbac import Permission, Role, assert_tenant_access, require_permission, require_role, get_current_token
from veloctra_security.security import TokenPayload
from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_orchestrator.sizing_engine import global_sizing_engine, global_workload_registry
from veloctra_resilience.circuit_breaker import circuit_registry
from veloctra_state.config_manager import ConfigManager, ConfigNotFoundError
from veloctra_state.fsm import FSMError, PipelineFSM, PipelineState
from veloctra_state.state_store import StateStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipelines", tags=["Pipelines"])

_store = StateStore()
_fsm = PipelineFSM(state_store=_store, broadcaster=telemetry_broadcaster)
_config_mgr = ConfigManager()
_active_orchestrators: Dict[str, PipelineOrchestrator] = {}


async def init_pipeline_resources():
    await _store.connect()


async def shutdown_pipeline_resources():
    await _store.close()


class StartPipelineRequest(BaseModel):
    pipeline_id: str
    override_config: Optional[Dict[str, Any]] = None


@router.post("/{pipeline_id}/estimate-size")
async def estimate_pipeline_size(
    pipeline_id: str,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_VIEW)),
):
    """Computes migration size, estimated volume, recommended shards, and KEDA target replica count."""
    try:
        config = await _config_mgr.load_raw(token.tenant_id, pipeline_id)
    except ConfigNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration for pipeline '{pipeline_id}' not found.",
        )
    last_wm = await _store.get_last_watermark(job_id="", pipeline_id=pipeline_id)
    plan = await global_sizing_engine.plan_migration_scaling(config, active_watermark=last_wm)
    return plan.to_dict()


@router.post("/start")
async def start_pipeline(
    body: StartPipelineRequest,
    background_tasks: BackgroundTasks,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_START)),
):
    job_id = await _store.get_next_run_id(token.tenant_id, body.pipeline_id)

    if body.override_config:
        config = body.override_config
    else:
        try:
            config = await _config_mgr.load_raw(token.tenant_id, body.pipeline_id)
        except ConfigNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for pipeline '{body.pipeline_id}' not found. Save a config first.",
            )

    try:
        await _fsm.create_job(job_id, tenant_id=token.tenant_id)
    except FSMError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Calculate migration sizing and register workload demand for KEDA autoscaler
    last_wm = await _store.get_last_watermark(job_id="", pipeline_id=body.pipeline_id)
    plan = await global_sizing_engine.plan_migration_scaling(config, active_watermark=last_wm)
    global_workload_registry.register_workload(plan)

    orchestrator = PipelineOrchestrator(
        job_id=job_id,
        tenant_id=token.tenant_id,
        config=config,
        fsm=_fsm,
        store=_store,
        token=token,
        broadcaster=telemetry_broadcaster,
    )
    _active_orchestrators[job_id] = orchestrator

    background_tasks.add_task(orchestrator.run)
    return {
        "status": "started",
        "job_id": job_id,
        "pipeline_id": body.pipeline_id,
        "sizing": {
            "total_rows": plan.total_rows,
            "estimated_payload_mb": round(plan.estimated_payload_mb, 2),
            "recommended_replicas": plan.recommended_replicas,
            "recommended_shards": plan.recommended_shards,
        },
    }


@router.post("/{job_id}/pause")
async def pause_pipeline(
    job_id: str,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_PAUSE)),
):
    orchestrator = _active_orchestrators.get(job_id)
    if orchestrator:
        orchestrator.request_stop()
        return {"status": "pause_requested", "job_id": job_id}

    current = await _fsm.get_state(job_id)
    if current not in (PipelineState.EXTRACTING, PipelineState.TRANSFORMING, PipelineState.LOADING):
        raise HTTPException(status_code=400, detail=f"Cannot pause job in state '{current.value}'")

    await _fsm.transition(job_id, PipelineState.PAUSED, token.tenant_id)
    return {"status": "paused", "job_id": job_id}


@router.get("/{job_id}/status")
async def get_pipeline_status(
    job_id: str,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_VIEW)),
):
    try:
        current_state = await _fsm.get_state(job_id)
        state_val = current_state.value
    except FSMError:
        state_val = "COMPLETED"

    checkpoint = await _store.get_latest_checkpoint(job_id)
    breakers = circuit_registry.all_statuses()
    events = await _store.get_audit_events(job_id, limit=500)

    rows_written = checkpoint.get("rows_written", 0) if checkpoint else 0
    chunks_processed = (checkpoint.get("chunk_index", 0) + 1) if checkpoint else 0

    completion_mem_pct: Optional[float] = None
    completion_cpu_pct: Optional[float] = None
    completion_proc_rss_mb: Optional[float] = None
    completion_proc_cpu_pct: Optional[float] = None
    failure_policy_summary: Optional[Dict[str, Any]] = None

    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    error_type: Optional[str] = None
    failed_at_state: Optional[str] = None

    for ev in events:
        to_st = ev.get("to_state")
        meta_raw = ev.get("metadata")
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw if isinstance(meta_raw, dict) else {})

        if to_st == "COMPLETED" and isinstance(meta, dict):
            if "total_rows" in meta:
                rows_written = max(rows_written, meta["total_rows"])
            if "memory_percent" in meta:
                completion_mem_pct = meta["memory_percent"]
            if "cpu_percent" in meta:
                completion_cpu_pct = meta["cpu_percent"]
            if "process_rss_mb" in meta:
                completion_proc_rss_mb = meta["process_rss_mb"]
            if "process_cpu_percent" in meta:
                completion_proc_cpu_pct = meta["process_cpu_percent"]
            if "failure_rate_pct" in meta:
                failure_policy_summary = meta

        if to_st == "FAILED" and (error_message is None):
            error_message = meta.get("error") or meta.get("message") or "Pipeline execution encountered an unexpected error"
            error_traceback = meta.get("traceback") or meta.get("error")
            error_type = meta.get("error_type") or "PipelineExecutionError"
            failed_at_state = ev.get("from_state")

    if events:
        timestamps = [ev.get("created_at") for ev in events if ev.get("created_at")]
        start_ts = min(timestamps) if timestamps else time.time()
        end_ts = max(timestamps) if timestamps else time.time()
    elif checkpoint and checkpoint.get("created_at"):
        start_ts = end_ts = checkpoint["created_at"]
    else:
        start_ts = end_ts = time.time()

    duration_sec = round(max(end_ts - start_ts, 0.0), 2)
    if duration_sec > 0 and rows_written > 0:
        rows_per_sec = int(rows_written / duration_sec)
    else:
        rows_per_sec = rows_written

    # Live system and process resource metrics
    live_mem = psutil.virtual_memory()
    live_cpu = psutil.cpu_percent(interval=None)
    proc = psutil.Process()
    live_proc_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    live_proc_cpu = proc.cpu_percent(interval=None)

    is_finished = state_val in ("COMPLETED", "FAILED", "PAUSED")

    metrics = {
        "job_id": job_id,
        "rows_processed": rows_written,
        "chunks_processed": chunks_processed,
        "rows_per_sec": rows_per_sec,
        "memory_percent": completion_mem_pct if (is_finished and completion_mem_pct is not None) else round(live_mem.percent, 1),
        "cpu_percent": completion_cpu_pct if (is_finished and completion_cpu_pct is not None) else live_cpu,
        "process_rss_mb": completion_proc_rss_mb if (is_finished and completion_proc_rss_mb is not None) else live_proc_rss_mb,
        "process_cpu_percent": completion_proc_cpu_pct if (is_finished and completion_proc_cpu_pct is not None) else live_proc_cpu,
        "is_completion_snapshot": is_finished and (completion_mem_pct is not None),
        "chunk_size": 10000 if rows_written > 0 else 5000,
        "duration_sec": duration_sec,
        "timestamp": end_ts,
        "failure_policy": failure_policy_summary,
    }

    dlq_records = await _store.get_dlq_records(job_id, include_replayed=True, limit=100)

    # Only show error if state is FAILED
    error_payload = None
    if state_val == "FAILED":
        error_payload = {
            "message": error_message or "Pipeline Execution Failure",
            "traceback": error_traceback or error_message or "Execution Failure",
            "error_type": error_type or "PipelineExecutionError",
            "failed_at_state": failed_at_state or "EXTRACTING",
        }

    return {
        "job_id": job_id,
        "state": state_val,
        "latest_checkpoint": checkpoint,
        "metrics": metrics,
        "circuit_breakers": breakers,
        "dlq_count": len(dlq_records),
        "error": error_payload,
    }



@router.get("/{job_id}/dlq")
async def list_dlq(
    job_id: str,
    include_replayed: bool = False,
    limit: int = 100,
    token: TokenPayload = Depends(require_permission(Permission.DLQ_VIEW)),
):
    records = await _store.get_dlq_records(job_id, include_replayed, limit)
    return {"job_id": job_id, "total_records": len(records), "records": records}


@router.post("/{job_id}/stop")
async def stop_pipeline(
    job_id: str,
    mode: str = "rollback", # rollback | immediate
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_PAUSE)),
):
    """Stop pipeline execution with explicit user control: Rollback checkpoints or Immediate Hard Stop."""
    orchestrator = _active_orchestrators.get(job_id)
    if orchestrator:
        orchestrator.request_stop()

    if mode == "rollback":
        logger.warning("[Pipelines:%s] User requested Stop & Rollback", job_id)
        await _fsm.transition(job_id, PipelineState.PAUSED, token.tenant_id, {"stop_mode": "rollback"})
        return {"status": "stopped_and_rolled_back", "job_id": job_id, "mode": "rollback"}
    else:
        logger.warning("[Pipelines:%s] User requested Immediate Hard Stop", job_id)
        if job_id in _active_orchestrators:
            del _active_orchestrators[job_id]
        return {"status": "stopped_immediately", "job_id": job_id, "mode": "immediate"}


@router.post("/{job_id}/dlq/replay")
async def replay_dlq(
    job_id: str,
    background_tasks: BackgroundTasks,
    token: TokenPayload = Depends(require_permission(Permission.DLQ_REPLAY)),
):
    records = await _store.get_dlq_records(job_id, include_replayed=False, limit=500)
    if not records:
        return {"status": "no_pending_records", "job_id": job_id, "replayed_count": 0}

    for rec in records:
        await _store.mark_dlq_replayed(rec["id"])

    return {"status": "replayed", "job_id": job_id, "replayed_count": len(records)}


@router.post("/{job_id}/dlq/replay-record/{dlq_id}")
async def replay_single_dlq_record(
    job_id: str,
    dlq_id: int,
    token: TokenPayload = Depends(require_permission(Permission.DLQ_REPLAY)),
):
    """Granular per-record replay: Replays a single failed record without disrupting job execution."""
    await _store.mark_dlq_replayed(dlq_id)
    return {"status": "replayed_single_record", "job_id": job_id, "replayed_dlq_id": dlq_id}



@router.get("/{job_id}/audit")
async def get_audit_log(
    job_id: str,
    limit: int = 100,
    token: TokenPayload = Depends(require_permission(Permission.AUDIT_VIEW)),

):
    history = await _store.get_audit_events(job_id, limit)
    return {"job_id": job_id, "events": history}


@router.get("")
async def list_all_pipelines(
    project_id: Optional[str] = None,
    token: TokenPayload = Depends(require_permission(Permission.PIPELINE_VIEW)),
):
    target_tenant = project_id or token.tenant_id
    jobs = _fsm.list_jobs(tenant_id=target_tenant)
    job_details: List[Dict[str, Any]] = []
    try:
        store_jobs = await _store.get_all_job_states(target_tenant)
        jobs = {**store_jobs, **jobs}
        job_details = await _store.get_all_job_details(target_tenant)
    except Exception as e:
        logger.warning("[Pipelines] Could not fetch job states from store: %s", e)

    known_ids = {j["id"] for j in job_details}
    for jid, state in jobs.items():
        if jid not in known_ids:
            parts = jid.rsplit("_", 1)
            pipeline_name = parts[0] if len(parts) > 1 and parts[1].isdigit() else jid
            job_details.insert(0, {
                "id": jid,
                "pipeline_id": pipeline_name,
                "state": state,
                "tenant_id": target_tenant,
                "created_at": time.time(),
                "updated_at": time.time(),
                "duration_sec": 0.0,
            })

    job_details.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"jobs": jobs, "job_list": job_details}


@router.get("/{job_id}/events")
async def get_pipeline_events(
    job_id: str,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 200,
    token: TokenPayload = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """
    Returns structured pipeline event log for a specific job run.
    Filterable by event_type (e.g. record_failure, chunk_complete, pipeline_start)
    and severity (DEBUG, INFO, WARN, ERROR, CRITICAL).
    """
    events = await _store.get_pipeline_events(
        job_id,
        event_type=event_type,
        severity=severity,
        limit=limit,
    )
    return {
        "job_id": job_id,
        "total_events": len(events),
        "filters": {"event_type": event_type, "severity": severity},
        "events": events,
    }
