"""
tests/test_data_quality_orchestrator.py
=======================================
Tests verifying DataQualityValidator assertions inside the PipelineOrchestrator loop.
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

    # Initialize source table with 1 valid row and 2 non-compliant rows
    with sqlite3.connect(src_path) as conn:
        conn.execute("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                age INTEGER
            )
        """)
        conn.execute("INSERT INTO customers VALUES (1, 'Alice', 'alice@company.com', 30)")
        conn.execute("INSERT INTO customers VALUES (2, 'Bob', 'invalid-email-format', 45)")
        conn.execute("INSERT INTO customers VALUES (3, 'Charlie', NULL, 150)")  # null email, age > 120
        conn.commit()

    with sqlite3.connect(dst_path) as conn:
        conn.execute("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                name TEXT,
                email TEXT,
                age INTEGER
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
async def test_orchestrator_data_quality_dlq_isolation(temp_db_paths):
    src_path, dst_path, state_path = temp_db_paths
    pipeline_id = "test_dq_pipeline"
    tenant_id = "tenant_dq"

    store = StateStore(adapter_type="sqlite", db_path=state_path)
    await store.connect()
    fsm = PipelineFSM()

    config = {
        "pipeline_id": pipeline_id,
        "tenant_id": tenant_id,
        "data_quality": {
            "strict": False,
            "not_null": ["email"],
            "max_value": {"age": 120},
            "regex_match": {"email": r"^[^@]+@[^@]+\.[^@]+$"},
        },
        "sources": [
            {
                "name": "src_cust",
                "type": "database",
                "connection_string": f"sqlite:///{src_path}",
                "query": "SELECT id, name, email, age FROM customers",
                "chunk_size": 10,
            }
        ],
        "destinations": [
            {
                "name": "dst_cust",
                "type": "database",
                "connection_string": f"sqlite:///{dst_path}",
                "table": "customers",
                "match_keys": ["id"],
            }
        ],
    }

    job_id = f"{pipeline_id}_run1"
    await fsm.create_job(job_id, tenant_id)
    orch = PipelineOrchestrator(
        job_id=job_id,
        tenant_id=tenant_id,
        config=config,
        fsm=fsm,
        store=store,
    )

    rows = await orch.run()
    # Exactly 1 valid row (Alice) should be processed and written
    assert rows == 1

    # Verify destination has only 1 row
    with sqlite3.connect(dst_path) as conn:
        cursor = conn.execute("SELECT id, name FROM customers")
        records = cursor.fetchall()
        assert len(records) == 1
        assert records[0] == (1, "Alice")

    # Verify DLQ received the 2 non-compliant rows with contract violation traces
    dlq_items = await store.get_dlq_records(job_id)
    assert len(dlq_items) == 2
    assert any("DataQualityViolation" in item["error_trace"] for item in dlq_items)

    await store.close()
