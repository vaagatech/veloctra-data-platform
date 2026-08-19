"""
veloctra_state/fsm.py
=====================
Deterministic 11-State Finite State Machine for Veloctra Data Platform.
"""

from __future__ import annotations

import logging, time
from enum import Enum
from typing import Callable, Dict, FrozenSet, List, Optional


from veloctra_security.security import sanitize_config
from veloctra_state.state_store import StateStore

logger = logging.getLogger(__name__)


class PipelineState(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    TRANSFORMING = "TRANSFORMING"
    LOADING = "LOADING"
    CHECKPOINTING = "CHECKPOINTING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    DLQ_ROUTED = "DLQ_ROUTED"


_TRANSITIONS: Dict[PipelineState, FrozenSet[PipelineState]] = {
    PipelineState.CREATED: frozenset({PipelineState.VALIDATING}),
    PipelineState.VALIDATING: frozenset({PipelineState.EXTRACTING, PipelineState.FAILED}),
    PipelineState.EXTRACTING: frozenset({
        PipelineState.TRANSFORMING,
        PipelineState.CHECKPOINTING,
        PipelineState.COMPLETED,
        PipelineState.RETRYING,
        PipelineState.PAUSED,
        PipelineState.FAILED,
        PipelineState.DLQ_ROUTED,
    }),
    PipelineState.TRANSFORMING: frozenset({
        PipelineState.LOADING,
        PipelineState.RETRYING,
        PipelineState.PAUSED,
        PipelineState.FAILED,
        PipelineState.DLQ_ROUTED,
    }),
    PipelineState.LOADING: frozenset({
        PipelineState.CHECKPOINTING,
        PipelineState.RETRYING,
        PipelineState.PAUSED,
        PipelineState.FAILED,
        PipelineState.DLQ_ROUTED,
    }),
    PipelineState.CHECKPOINTING: frozenset({
        PipelineState.EXTRACTING,
        PipelineState.TRANSFORMING,
        PipelineState.LOADING,
        PipelineState.COMPLETED,
        PipelineState.RETRYING,
        PipelineState.FAILED,
        PipelineState.DLQ_ROUTED,
    }),

    PipelineState.RETRYING: frozenset({PipelineState.EXTRACTING, PipelineState.FAILED}),
    PipelineState.PAUSED: frozenset({PipelineState.EXTRACTING, PipelineState.FAILED}),
    PipelineState.DLQ_ROUTED: frozenset({
        PipelineState.EXTRACTING,
        PipelineState.TRANSFORMING,
        PipelineState.LOADING,
        PipelineState.COMPLETED,
        PipelineState.FAILED,
    }),

    PipelineState.COMPLETED: frozenset(),
    PipelineState.FAILED: frozenset(),
}

TERMINAL_STATES: FrozenSet[PipelineState] = frozenset({
    PipelineState.COMPLETED,
    PipelineState.FAILED,
})


class FSMError(Exception):
    """Base exception for FSM operations."""


class InvalidTransitionError(FSMError):
    """Raised when an illegal transition is attempted."""


class JobNotFoundError(FSMError):
    """Raised when an operation targets an uncreated job."""


class PipelineFSM:
    def __init__(
        self,
        state_store: Optional[StateStore] = None,
        broadcaster: Optional[Callable] = None,
    ):
        self._jobs: Dict[str, PipelineState] = {}
        self._job_tenants: Dict[str, str] = {}
        self._store = state_store
        self._broadcaster = broadcaster

    async def create_job(self, job_id: str, tenant_id: str = "default") -> None:
        self._job_tenants[job_id] = tenant_id
        if job_id in self._jobs:
            logger.warning("[FSM:%s] Job already exists in state %s — ignoring create", job_id, self._jobs[job_id].value)
            return

        self._jobs[job_id] = PipelineState.CREATED
        logger.info("[FSM:%s] Created job (tenant=%s)", job_id, tenant_id)

        if self._store:
            await self._store.log_fsm_transition(
                job_id=job_id,
                tenant_id=tenant_id,
                from_state="<NONE>",
                to_state=PipelineState.CREATED.value,
            )

        await self._notify(job_id, PipelineState.CREATED)

    async def transition(
        self,
        job_id: str,
        to_state: PipelineState,
        tenant_id: str = "default",
        metadata: Optional[Dict] = None,
    ) -> PipelineState:
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job '{job_id}' is not tracked by this FSM.")

        from_state = self._jobs[job_id]
        if from_state in TERMINAL_STATES:
            raise InvalidTransitionError(
                f"Job '{job_id}' is in terminal state '{from_state.value}' and cannot transition."
            )

        allowed = _TRANSITIONS.get(from_state, frozenset())
        if to_state not in allowed:
            raise InvalidTransitionError(
                f"Illegal FSM transition for job '{job_id}': {from_state.value} → {to_state.value}. "
                f"Allowed from {from_state.value}: {[s.value for s in allowed]}"
            )

        self._jobs[job_id] = to_state
        logger.info("[FSM:%s] Transition: %s → %s", job_id, from_state.value, to_state.value)

        sanitised_meta = sanitize_config(metadata or {})

        if self._store:
            await self._store.log_fsm_transition(
                job_id=job_id,
                tenant_id=tenant_id,
                from_state=from_state.value,
                to_state=to_state.value,
                metadata=sanitised_meta,
            )

        await self._notify(job_id, to_state, sanitised_meta)
        return to_state

    async def get_state(self, job_id: str) -> PipelineState:
        if job_id not in self._jobs:
            raise JobNotFoundError(f"Job '{job_id}' not found.")
        return self._jobs[job_id]

    async def is_terminal(self, job_id: str) -> bool:
        state = await self.get_state(job_id)
        return state in TERMINAL_STATES

    def list_jobs(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        if tenant_id:
            return {
                jid: state.value
                for jid, state in self._jobs.items()
                if self._job_tenants.get(jid) == tenant_id or tenant_id in jid
            }
        return {jid: state.value for jid, state in self._jobs.items()}


    async def _notify(self, job_id: str, state: PipelineState, metadata: Optional[Dict] = None) -> None:
        if self._broadcaster is None:
            return
        event = {
            "event": "fsm_transition",
            "job_id": job_id,
            "state": state.value,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        try:
            await self._broadcaster(job_id, event)
        except Exception as exc:
            logger.warning("[FSM:%s] Telemetry broadcast failed: %s", job_id, exc)
