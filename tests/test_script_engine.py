"""
tests/test_script_engine.py
===========================
Tests for ScriptTransformEngine (inline scripts, pandas, polars, timeouts, and error handling).
"""

import pytest
import pyarrow as pa
from veloctra_transformers.script_engine import ScriptTransformEngine, ScriptExecutionError


def test_script_engine_inline_arrow():
    code = """
import pyarrow as pa
import pyarrow.compute as pc

def transform(batch: pa.RecordBatch) -> pa.RecordBatch:
    # Double the amount column
    amt_col = batch["amount"]
    doubled = pc.multiply(amt_col, 2.0)
    schema = batch.schema
    idx = schema.get_field_index("amount")
    return batch.set_column(idx, "amount", doubled)
"""
    engine = ScriptTransformEngine(script_code=code)
    batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 3],
        "amount": [10.0, 20.0, 30.0],
    })

    result = engine.process_batch_sync(batch)
    assert result.num_rows == 3
    assert result["amount"].to_pylist() == [20.0, 40.0, 60.0]


def test_script_engine_inline_pandas():
    code = """
def transform_df(df):
    df["risk_score"] = df["amount"] * 0.1
    df["flagged"] = df["risk_score"] > 2.0
    return df
"""
    engine = ScriptTransformEngine(script_code=code)
    batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 3],
        "amount": [10.0, 25.0, 50.0],
    })

    result = engine.process_batch_sync(batch)
    assert result.num_rows == 3
    assert "risk_score" in result.schema.names
    assert "flagged" in result.schema.names
    assert result["flagged"].to_pylist() == [False, True, True]


def test_script_engine_inline_records():
    code = """
def transform_records(records):
    for r in records:
        r["upper_name"] = r["name"].upper()
    return records
"""
    engine = ScriptTransformEngine(script_code=code)
    batch = pa.RecordBatch.from_pydict({
        "id": [1, 2],
        "name": ["alice", "bob"],
    })

    result = engine.process_batch_sync(batch)
    assert result.num_rows == 2
    assert result["upper_name"].to_pylist() == ["ALICE", "BOB"]


def test_script_engine_compilation_error():
    code = """
def transform(batch
    syntax error here
"""
    with pytest.raises(ScriptExecutionError) as exc_info:
        ScriptTransformEngine(script_code=code)
    assert "Compilation error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_script_engine_timeout():
    code = """
import time

def transform(batch):
    time.sleep(2.0)
    return batch
"""
    engine = ScriptTransformEngine(script_code=code, timeout_seconds=0.2)
    batch = pa.RecordBatch.from_pydict({"id": [1, 2]})

    with pytest.raises(ScriptExecutionError) as exc_info:
        await engine.process_batch(batch)
    assert "timed out" in str(exc_info.value)
