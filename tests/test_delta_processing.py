"""
tests/test_delta_processing.py
==============================
Tests for Delta Processing, High-Watermark CDC, and Idempotent UPSERT Sync.
"""

import asyncio
import os
import sqlite3
import tempfile
import pytest
import pyarrow as pa

from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM
from veloctra_state.state_store import StateStore


@pytest.fixture
def temp_db_paths():
    fd1, src_path = tempfile.mkstemp(suffix="_src.db")
    fd2, dst_path = tempfile.mkstemp(suffix="_dst.db")
    fd3, state_path = tempfile.mkstemp(suffix="_state.db")
    os.close(fd1)
    os.close(fd2)
    os.close(fd3)

    # Initialize source table with timestamps
    with sqlite3.connect(src_path) as conn:
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com', '2026-01-01T10:00:00')")
        conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@test.com', '2026-01-02T10:00:00')")
        conn.execute("INSERT INTO users VALUES (3, 'Charlie', 'charlie@test.com', '2026-01-03T10:00:00')")
        conn.commit()

    # Initialize destination table
    with sqlite3.connect(dst_path) as conn:
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

    yield src_path, dst_path, state_path

    for p in (src_path, dst_path, state_path):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_delta_processing_incremental_watermark_sync(temp_db_paths):
    src_path, dst_path, state_path = temp_db_paths
    pipeline_id = "test_delta_sync"
    tenant_id = "tenant_delta_test"

    store = StateStore(adapter_type="sqlite", db_path=state_path)
    await store.connect()
    fsm = PipelineFSM()

    config_run_1 = {
        "pipeline_id": pipeline_id,
        "tenant_id": tenant_id,
        "sources": [
            {
                "name": "src_users",
                "type": "database",
                "connection_string": f"sqlite:///{src_path}",
                "query": "SELECT id, name, email, updated_at FROM users",
                "delta": {
                    "enabled": True,
                    "watermark_column": "updated_at",
                    "watermark_type": "timestamp",
                    "initial_watermark": "2025-01-01T00:00:00",
                },
                "chunk_size": 2,
            }
        ],
        "destinations": [
            {
                "name": "dst_users",
                "type": "database",
                "connection_string": f"sqlite:///{dst_path}",
                "table": "users",
                "match_keys": ["id"],
            }
        ],
    }

    # 1. First execution: Syncs all 3 records
    job_1 = f"{pipeline_id}_run1"
    await fsm.create_job(job_1, tenant_id)
    orch_1 = PipelineOrchestrator(
        job_id=job_1,
        tenant_id=tenant_id,
        config=config_run_1,
        fsm=fsm,
        store=store,
    )
    rows_1 = await orch_1.run()
    assert rows_1 == 3

    # Check high-watermark recorded
    latest_wm = await store.get_last_watermark(job_1, pipeline_id=pipeline_id)
    assert latest_wm == "2026-01-03T10:00:00"

    # Verify destination table has 3 rows
    with sqlite3.connect(dst_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        assert cursor.fetchone()[0] == 3

    # 2. Insert new record and update an existing record in source
    with sqlite3.connect(src_path) as conn:
        # Update Alice with new timestamp
        conn.execute("UPDATE users SET name = 'Alice Updated', updated_at = '2026-01-04T12:00:00' WHERE id = 1")
        # Add new user David
        conn.execute("INSERT INTO users VALUES (4, 'David', 'david@test.com', '2026-01-05T14:00:00')")
        conn.commit()

    # 3. Second execution: Delta sync should only extract the 2 records > '2026-01-03T10:00:00'
    job_2 = f"{pipeline_id}_run2"
    await fsm.create_job(job_2, tenant_id)
    config_run_2 = dict(config_run_1)
    orch_2 = PipelineOrchestrator(
        job_id=job_2,
        tenant_id=tenant_id,
        config=config_run_2,
        fsm=fsm,
        store=store,
    )
    rows_2 = await orch_2.run()
    assert rows_2 == 2

    # Verify updated watermark
    latest_wm_2 = await store.get_last_watermark(job_2, pipeline_id=pipeline_id)
    assert latest_wm_2 == "2026-01-05T14:00:00"

    # Verify destination table content: Exactly 4 distinct records (Alice updated in place, David added)
    with sqlite3.connect(dst_path) as conn:
        cursor = conn.execute("SELECT id, name, updated_at FROM users ORDER BY id ASC")
        rows = cursor.fetchall()
        assert len(rows) == 4
        assert rows[0] == (1, "Alice Updated", "2026-01-04T12:00:00")
        assert rows[1] == (2, "Bob", "2026-01-02T10:00:00")
        assert rows[2] == (3, "Charlie", "2026-01-03T10:00:00")
        assert rows[3] == (4, "David", "2026-01-05T14:00:00")

    await store.close()


@pytest.mark.asyncio
async def test_delta_processing_numeric_id_watermark(temp_db_paths):
    src_path, dst_path, state_path = temp_db_paths
    pipeline_id = "test_numeric_delta"
    tenant_id = "tenant_numeric_test"

    store = StateStore(adapter_type="sqlite", db_path=state_path)
    await store.connect()
    fsm = PipelineFSM()

    config = {
        "pipeline_id": pipeline_id,
        "tenant_id": tenant_id,
        "sources": [
            {
                "name": "src_users",
                "type": "database",
                "connection_string": f"sqlite:///{src_path}",
                "query": "SELECT id, name, email FROM users",
                "delta": {
                    "enabled": True,
                    "watermark_column": "id",
                    "watermark_type": "integer",
                    "initial_watermark": 1,
                },
                "chunk_size": 5,
            }
        ],
        "destinations": [
            {
                "name": "dst_users",
                "type": "database",
                "connection_string": f"sqlite:///{dst_path}",
                "table": "users",
                "match_keys": ["id"],
            }
        ],
    }

    job_1 = f"{pipeline_id}_run1"
    await fsm.create_job(job_1, tenant_id)
    orch = PipelineOrchestrator(
        job_id=job_1,
        tenant_id=tenant_id,
        config=config,
        fsm=fsm,
        store=store,
    )
    # initial_watermark was 1, so only rows with id > 1 (ids 2 and 3) should be synced
    rows = await orch.run()
    assert rows == 2

    latest_wm = await store.get_last_watermark(job_1, pipeline_id=pipeline_id)
    assert latest_wm == "3"

    await store.close()
