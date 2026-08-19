"""
tests/test_script_orchestrator.py
=================================
Tests verifying custom Python script transformations within PipelineOrchestrator.
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

    with sqlite3.connect(src_path) as conn:
        conn.execute("CREATE TABLE claims (id INTEGER PRIMARY KEY, patient_id TEXT, amount REAL, days INTEGER)")
        conn.execute("INSERT INTO claims VALUES (1, 'P100', 5000.0, 3)")
        conn.execute("INSERT INTO claims VALUES (2, 'P200', 12000.0, 10)")
        conn.commit()

    with sqlite3.connect(dst_path) as conn:
        conn.execute("CREATE TABLE scored_claims (id INTEGER PRIMARY KEY, patient_id TEXT, amount REAL, days INTEGER, risk_tier TEXT, is_high_risk INTEGER)")
        conn.commit()

    yield src_path, dst_path, state_path

    for p in (src_path, dst_path, state_path):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_orchestrator_custom_script_execution(temp_db_paths):
    src_path, dst_path, state_path = temp_db_paths
    pipeline_id = "test_custom_script_pipeline"
    tenant_id = "tenant_custom_script"

    store = StateStore(adapter_type="sqlite", db_path=state_path)
    await store.connect()
    fsm = PipelineFSM()

    custom_script_code = """
def transform_df(df):
    df["risk_tier"] = df["days"].apply(lambda d: "HIGH" if d > 7 else "STANDARD")
    df["is_high_risk"] = (df["amount"] > 10000.0).astype(int)
    return df
"""

    config = {
        "pipeline_id": pipeline_id,
        "tenant_id": tenant_id,
        "custom_script": {
            "code": custom_script_code,
            "timeout_seconds": 15.0,
        },
        "sources": [
            {
                "name": "src_claims",
                "type": "database",
                "connection_string": f"sqlite:///{src_path}",
                "query": "SELECT id, patient_id, amount, days FROM claims",
                "chunk_size": 10,
            }
        ],
        "destinations": [
            {
                "name": "dst_scored",
                "type": "database",
                "connection_string": f"sqlite:///{dst_path}",
                "table": "scored_claims",
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
    assert rows == 2

    # Verify scored destination records
    with sqlite3.connect(dst_path) as conn:
        cursor = conn.execute("SELECT id, patient_id, risk_tier, is_high_risk FROM scored_claims ORDER BY id ASC")
        records = cursor.fetchall()
        assert len(records) == 2
        assert records[0] == (1, "P100", "STANDARD", 0)
        assert records[1] == (2, "P200", "HIGH", 1)

    await store.close()
