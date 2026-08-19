"""
tests/test_record_failure_isolation.py
=======================================
Unit tests verifying per-record poison-pill isolation to DLQ without dropping valid records.
"""

import pytest
import pyarrow as pa
from unittest.mock import AsyncMock, MagicMock
from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM, PipelineState


@pytest.mark.asyncio
async def test_fallback_row_by_row_transform_isolates_poison_pill():
    """Verify that if row 2 in a batch of 4 is corrupt, row 2 is routed to DLQ while rows 1, 3, 4 succeed."""
    mock_store = AsyncMock()
    mock_store.push_dlq.return_value = 101
    mock_fsm = AsyncMock()

    orchestrator = PipelineOrchestrator(
        job_id="test_poison_job",
        tenant_id="test_tenant",
        config={},
        fsm=mock_fsm,
        store=mock_store,
    )

    # 4 rows batch
    batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "BAD_POISON", "Charlie", "David"],
    })

    mock_rules_engine = MagicMock()
    mock_rules_engine.apply_rules.side_effect = lambda b: b

    mock_enrichment_engine = AsyncMock()
    mock_enrichment_engine.apply_enrichments.side_effect = lambda b: b

    # Transform engine fails specifically on "BAD_POISON"
    mock_transform_engine = MagicMock()
    def fake_process_batch(b, plugins):
        val = b.column("name")[0].as_py()
        if val == "BAD_POISON":
            raise ValueError("Corrupted record payload")
        return b

    mock_transform_engine.process_batch.side_effect = fake_process_batch

    result = await orchestrator._fallback_row_by_row_transform(
        raw_batch=batch,
        rules_engine=mock_rules_engine,
        enrichment_engine=mock_enrichment_engine,
        transform_engine=mock_transform_engine,
        cipher_engine=None,
        enc_cfg={},
        custom_plugins={},
        chunk_idx=0,
    )

    # Valid rows 1, 3, 4 should be preserved (3 rows)
    assert result.num_rows == 3
    assert result.column("id").to_pylist() == [1, 3, 4]
    assert result.column("name").to_pylist() == ["Alice", "Charlie", "David"]

    # DLQ should have been called once for the bad row
    mock_store.push_dlq.assert_called_once()
    args = mock_store.push_dlq.call_args[0]
    assert args[0] == "test_poison_job"
    assert args[1] == "test_tenant"
    assert args[2]["name"] == "BAD_POISON"
    assert "Corrupted record payload" in args[3]


@pytest.mark.asyncio
async def test_fallback_row_by_row_load_isolates_db_error():
    """Verify that if loading row 2 fails on DB constraint, row 2 is routed to DLQ while rows 1 and 3 are loaded."""
    mock_store = AsyncMock()
    mock_store.push_dlq.return_value = 202
    mock_fsm = AsyncMock()

    orchestrator = PipelineOrchestrator(
        job_id="test_load_fail_job",
        tenant_id="test_tenant",
        config={},
        fsm=mock_fsm,
        store=mock_store,
    )

    batch = pa.RecordBatch.from_pydict({
        "id": [101, 102, 103],
        "val": ["good_1", "bad_unique_constraint_violation", "good_3"],
    })

    call_count = 0
    async def mock_load_fn(mini_b, dests, partitioner):
        nonlocal call_count
        call_count += 1
        if mini_b.column("val")[0].as_py() == "bad_unique_constraint_violation":
            raise RuntimeError("UNIQUE constraint failed: table.id")

    orchestrator._load = mock_load_fn

    loaded_count = await orchestrator._fallback_row_by_row_load(
        batch=batch,
        destinations=[{"type": "database"}],
        partitioner=None,
        chunk_idx=1,
    )

    # 2 rows succeeded, 1 failed
    assert loaded_count == 2
    assert mock_store.push_dlq.call_count == 1
    args = mock_store.push_dlq.call_args[0]
    assert args[2]["val"] == "bad_unique_constraint_violation"
    assert "UNIQUE constraint failed" in args[3]
