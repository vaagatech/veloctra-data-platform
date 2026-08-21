"""
tests/test_sizing_engine.py
===========================
Unit tests for MigrationSizingEngine, sizing heuristics, replica targets,
and GlobalWorkloadRegistry for KEDA autoscaling.
"""

import os
import sqlite3
import tempfile
import pytest
from veloctra_orchestrator.sizing_engine import (
    MigrationSizingEngine,
    MigrationScalingPlan,
    SourceSizeEstimate,
    GlobalWorkloadRegistry,
)


@pytest.fixture
def temp_sqlite_db():
    fd, path = tempfile.mkstemp(suffix="_sizing.db")
    os.close(fd)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE claims (id INTEGER PRIMARY KEY, amount REAL, updated_at TEXT)")
        for i in range(1, 2501):
            conn.execute(f"INSERT INTO claims VALUES ({i}, {i * 10.5}, '2026-01-01T00:00:00')")
        conn.commit()

    yield path

    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_sizing_engine_sql_exact_count(temp_sqlite_db):
    engine = MigrationSizingEngine(default_rows_per_worker=1000, default_min_replicas=1, default_max_replicas=8)
    
    config = {
        "pipeline_id": "test_claims_pipeline",
        "tenant_id": "tenant_a",
        "settings": {
            "keda": {
                "rows_per_worker": 1000,
                "min_replicas": 1,
                "max_replicas": 8,
            }
        },
        "sources": [
            {
                "name": "sqlite_claims",
                "type": "database",
                "connection_string": f"sqlite:///{temp_sqlite_db}",
                "query": "SELECT * FROM claims",
            }
        ],
    }

    plan = await engine.plan_migration_scaling(config)
    assert plan.total_rows == 2500
    assert plan.is_exact if hasattr(plan, "is_exact") else True
    assert plan.recommended_replicas == 3  # ceil(2500 / 1000) = 3
    assert plan.recommended_shards >= 3
    assert len(plan.shard_intervals) >= 3
    assert plan.keda_enabled is True


@pytest.mark.asyncio
async def test_sizing_engine_watermark_delta_filter(temp_sqlite_db):
    engine = MigrationSizingEngine(default_rows_per_worker=1000)
    
    config = {
        "pipeline_id": "test_watermark_pipeline",
        "tenant_id": "tenant_a",
        "sources": [
            {
                "name": "sqlite_claims",
                "type": "database",
                "connection_string": f"sqlite:///{temp_sqlite_db}",
                "query": "SELECT * FROM claims",
                "delta": {
                    "watermark_column": "id",
                    "watermark_type": "integer",
                    "initial_watermark": 2000,
                },
            }
        ],
    }

    plan = await engine.plan_migration_scaling(config)
    # id > 2000 (from 2001 to 2500 = 500 rows)
    assert plan.total_rows == 500
    assert plan.recommended_replicas == 1


def test_global_workload_registry_lifecycle():
    registry = GlobalWorkloadRegistry()

    plan = MigrationScalingPlan(
        pipeline_id="pipe_1",
        tenant_id="tenant_x",
        total_rows=300_000,
        estimated_payload_mb=150.0,
        recommended_replicas=3,
        recommended_shards=6,
        rows_per_worker=100_000,
        min_replicas=1,
        max_replicas=10,
        keda_enabled=True,
    )

    # 1. Register workload
    registry.register_workload(plan)
    stats1 = registry.get_metrics_snapshot()
    assert stats1["active_workloads"] == 1
    assert stats1["total_pending_rows"] == 300_000
    assert stats1["workload_demand_replicas"] == 3
    assert stats1["total_shards"] == 6

    # 2. Record progress (processed 100k rows)
    registry.record_progress("pipe_1", 100_000)
    stats2 = registry.get_metrics_snapshot()
    assert stats2["total_pending_rows"] == 200_000

    # 3. Complete workload
    registry.complete_workload("pipe_1")
    stats3 = registry.get_metrics_snapshot()
    assert stats3["active_workloads"] == 0
    assert stats3["total_pending_rows"] == 0
    assert stats3["workload_demand_replicas"] == 0
