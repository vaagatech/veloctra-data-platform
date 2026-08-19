"""
veloctra_api/routes_scripts.py
==============================
Custom Transformation Script validation and testing endpoints.
Allows UI and CI/CD tools to validate, lint, and dry-run transform scripts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import pyarrow as pa

from veloctra_transformers.script_engine import ScriptTransformEngine, ScriptExecutionError
from veloctra_security.rbac import Role, require_permission, Permission
from veloctra_security.security import TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scripts", tags=["Scripts"])


class ValidateScriptRequest(BaseModel):
    script_code: str = Field(..., description="Python transform script code")
    entrypoint: str = Field("transform", description="Function entrypoint name")
    sample_records: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional sample JSON records to dry-run transform against"
    )
    timeout_seconds: float = Field(10.0, ge=1.0, le=60.0)


class ValidateScriptResponse(BaseModel):
    valid: bool
    flavor: str
    sample_output: Optional[List[Dict[str, Any]]] = None
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None
    error_trace: Optional[str] = None


@router.post("/validate", response_model=ValidateScriptResponse)
async def validate_script(
    body: ValidateScriptRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_VALIDATE)),
):
    """
    Lints, compiles, and dry-runs a custom script against sample data.
    Ensures safe deployment for UI-created scripts and CI/CD pipelines.
    """
    try:
        engine = ScriptTransformEngine(
            script_code=body.script_code,
            entrypoint=body.entrypoint,
            timeout_seconds=body.timeout_seconds,
        )

        sample = body.sample_records or [
            {"id": 1, "name": "Acme Corp", "amount": 1500.50, "status": "PENDING"},
            {"id": 2, "name": "Global Tech", "amount": 3200.00, "status": "APPROVED"},
        ]

        batch = pa.RecordBatch.from_pylist(sample)
        t0 = time.perf_counter()
        out_batch = await engine.process_batch(batch)
        elapsed = (time.perf_counter() - t0) * 1000.0

        return ValidateScriptResponse(
            valid=True,
            flavor=engine._fn_flavor,
            sample_output=out_batch.to_pylist(),
            execution_time_ms=round(elapsed, 2),
        )

    except ScriptExecutionError as exc:
        return ValidateScriptResponse(
            valid=False,
            flavor="unknown",
            error=str(exc),
            error_trace=exc.error_trace,
        )
    except Exception as exc:
        return ValidateScriptResponse(
            valid=False,
            flavor="unknown",
            error=str(exc),
            error_trace=str(exc),
        )
