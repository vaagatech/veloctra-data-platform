"""
tests/test_prometheus_metrics.py
================================
Tests for the Prometheus /metrics exporter endpoint and KEDA scaling gauges.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from veloctra_api.main import app
from veloctra_orchestrator.sizing_engine import global_workload_registry, MigrationScalingPlan


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "veloctra_system_memory_percent" in text
        assert "veloctra_system_cpu_percent" in text
        assert "veloctra_process_memory_rss_bytes" in text
        assert "veloctra_migration_pending_rows" in text
        assert "veloctra_migration_workload_demand_replicas" in text
        assert "veloctra_migration_total_shards" in text
        assert "veloctra_migration_active_jobs" in text


@pytest.mark.asyncio
async def test_prometheus_keda_dynamic_gauge_emission():
    transport = ASGITransport(app=app)

    # 1. Register sample workload
    plan = MigrationScalingPlan(
        pipeline_id="claims_migration_batch",
        tenant_id="healthcare_tenant",
        total_rows=500_000,
        estimated_payload_mb=250.0,
        recommended_replicas=5,
        recommended_shards=10,
        rows_per_worker=100_000,
        min_replicas=1,
        max_replicas=16,
        keda_enabled=True,
    )
    global_workload_registry.register_workload(plan)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text1 = resp.text
        assert "veloctra_migration_pending_rows 500000" in text1
        assert "veloctra_migration_workload_demand_replicas 5" in text1
        assert "veloctra_migration_total_shards 10" in text1
        assert "veloctra_migration_active_jobs 1" in text1

        # 2. Record progress (processed 200k rows)
        global_workload_registry.record_progress("claims_migration_batch", 200_000)
        resp2 = await client.get("/metrics")
        text2 = resp2.text
        assert "veloctra_migration_pending_rows 300000" in text2

        # 3. Complete workload -> Gauge drops to 0 for KEDA scale-down
        global_workload_registry.complete_workload("claims_migration_batch")
        resp3 = await client.get("/metrics")
        text3 = resp3.text
        assert "veloctra_migration_pending_rows 0" in text3
        assert "veloctra_migration_workload_demand_replicas 0" in text3
        assert "veloctra_migration_active_jobs 0" in text3
