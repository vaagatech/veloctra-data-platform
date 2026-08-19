"""
tests/test_fsm.py
==================
Unit tests for the PipelineFSM state machine.
"""

import pytest
import pytest_asyncio
from veloctra_state.fsm import (
    PipelineFSM,
    PipelineState,
    InvalidTransitionError,
    JobNotFoundError,
)


TENANT = "test_tenant"


@pytest.fixture
def fsm():
    return PipelineFSM()


@pytest.mark.asyncio
async def test_create_job(fsm):
    await fsm.create_job("job-001", TENANT)
    state = await fsm.get_state("job-001")
    assert state == PipelineState.CREATED


@pytest.mark.asyncio
async def test_valid_transition_chain(fsm):
    await fsm.create_job("job-002", TENANT)
    await fsm.transition("job-002", PipelineState.VALIDATING, TENANT)
    await fsm.transition("job-002", PipelineState.EXTRACTING, TENANT)
    await fsm.transition("job-002", PipelineState.TRANSFORMING, TENANT)
    await fsm.transition("job-002", PipelineState.LOADING, TENANT)
    await fsm.transition("job-002", PipelineState.CHECKPOINTING, TENANT)
    await fsm.transition("job-002", PipelineState.COMPLETED, TENANT)
    state = await fsm.get_state("job-002")
    assert state == PipelineState.COMPLETED


@pytest.mark.asyncio
async def test_illegal_transition_raises(fsm):
    await fsm.create_job("job-003", TENANT)
    # CREATED → LOADING is illegal
    with pytest.raises(InvalidTransitionError):
        await fsm.transition("job-003", PipelineState.LOADING, TENANT)


@pytest.mark.asyncio
async def test_terminal_state_no_exit(fsm):
    await fsm.create_job("job-004", TENANT)
    await fsm.transition("job-004", PipelineState.VALIDATING, TENANT)
    await fsm.transition("job-004", PipelineState.FAILED, TENANT)
    # Cannot leave FAILED
    with pytest.raises(InvalidTransitionError):
        await fsm.transition("job-004", PipelineState.VALIDATING, TENANT)


@pytest.mark.asyncio
async def test_unknown_job_raises(fsm):
    with pytest.raises(JobNotFoundError):
        await fsm.get_state("nonexistent-job")


@pytest.mark.asyncio
async def test_retrying_resume(fsm):
    await fsm.create_job("job-005", TENANT)
    await fsm.transition("job-005", PipelineState.VALIDATING, TENANT)
    await fsm.transition("job-005", PipelineState.EXTRACTING, TENANT)
    await fsm.transition("job-005", PipelineState.RETRYING, TENANT)
    await fsm.transition("job-005", PipelineState.EXTRACTING, TENANT)  # resume
    state = await fsm.get_state("job-005")
    assert state == PipelineState.EXTRACTING


@pytest.mark.asyncio
async def test_is_terminal(fsm):
    await fsm.create_job("job-006", TENANT)
    assert not await fsm.is_terminal("job-006")
    await fsm.transition("job-006", PipelineState.VALIDATING, TENANT)
    await fsm.transition("job-006", PipelineState.EXTRACTING, TENANT)
    await fsm.transition("job-006", PipelineState.TRANSFORMING, TENANT)
    await fsm.transition("job-006", PipelineState.LOADING, TENANT)
    await fsm.transition("job-006", PipelineState.CHECKPOINTING, TENANT)
    await fsm.transition("job-006", PipelineState.COMPLETED, TENANT)
    assert await fsm.is_terminal("job-006")


@pytest.mark.asyncio
async def test_duplicate_create_is_noop(fsm):
    await fsm.create_job("job-007", TENANT)
    await fsm.create_job("job-007", TENANT)  # second create should be ignored
    state = await fsm.get_state("job-007")
    assert state == PipelineState.CREATED


@pytest.mark.asyncio
async def test_paused_resume(fsm):
    await fsm.create_job("job-008", TENANT)
    await fsm.transition("job-008", PipelineState.VALIDATING, TENANT)
    await fsm.transition("job-008", PipelineState.EXTRACTING, TENANT)
    await fsm.transition("job-008", PipelineState.PAUSED, TENANT)
    state = await fsm.get_state("job-008")
    assert state == PipelineState.PAUSED
    await fsm.transition("job-008", PipelineState.EXTRACTING, TENANT)
    state = await fsm.get_state("job-008")
    assert state == PipelineState.EXTRACTING
