"""
tests/test_cdc_engine.py
========================
Tests for ChecksumDiffCDC (Zero-Column / No-Timestamp CDC) and CDC Deletion handling.
"""

import pytest
import pyarrow as pa
from veloctra_connectors.cdc_engine import ChecksumDiffCDC, compute_row_hash


def test_checksum_diff_cdc_insert_update_delete():
    cdc = ChecksumDiffCDC(key_columns=["id"])

    # 1. Initial Snapshot: 3 rows
    initial_batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "balance": [100.0, 200.0, 300.0],
    })

    cdc_batch_1, state_1 = cdc.process_snapshot(initial_batch)

    # All 3 should be INSERT
    assert cdc_batch_1.num_rows == 3
    ops_1 = cdc_batch_1["_cdc_op"].to_pylist()
    assert ops_1 == ["INSERT", "INSERT", "INSERT"]
    assert len(state_1) == 3

    # 2. Second Snapshot:
    # - Row 1 (Alice): Unchanged
    # - Row 2 (Bob): In-place UPDATE (balance 200 -> 250)
    # - Row 3 (Charlie): DELETED (not in snapshot)
    # - Row 4 (David): INSERTED
    second_batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 4],
        "name": ["Alice", "Bob", "David"],
        "balance": [100.0, 250.0, 400.0],
    })

    cdc_batch_2, state_2 = cdc.process_snapshot(second_batch)

    # Should detect 3 change events (Update Bob, Delete Charlie, Insert David)
    assert cdc_batch_2.num_rows == 3
    pylist = cdc_batch_2.to_pylist()

    ops_by_id = {row["id"]: row["_cdc_op"] for row in pylist}
    assert ops_by_id[2] == "UPDATE"
    assert ops_by_id[4] == "INSERT"
    assert ops_by_id[3] == "DELETE"

    # State should now have keys 1, 2, 4
    assert set(state_2.keys()) == {"1", "2", "4"}
