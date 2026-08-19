"""
tests/test_observability_telemetry.py
======================================
Unit tests for zero-event-loss ring buffer and live observability endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from veloctra_api.main import app
from veloctra_api.websocket import TelemetryEventRingBuffer, manager
from veloctra_security.security import create_access_token


@pytest.fixture
def admin_token():
    return create_access_token(subject="admin", role="SuperAdmin", tenant_id="test_tenant")


@pytest.mark.asyncio
async def test_ring_buffer_retention_and_replay():
    buf = TelemetryEventRingBuffer(max_size=10)
    
    # Push 5 events for channel 'fin_job_1'
    for i in range(5):
        await buf.push("fin_job_1", {"event": "pipeline_progress", "chunk": i, "rows": i * 100})

    # Query channel
    events = await buf.get_recent_events("fin_job_1", limit=10)
    assert len(events) == 5
    assert events[0]["chunk"] == 0
    assert events[4]["chunk"] == 4

    # Query global
    global_events = await buf.get_recent_events("*", limit=10)
    assert len(global_events) == 5


def test_live_metrics_endpoint(admin_token):
    client = TestClient(app)
    response = client.get(
        "/metrics/live",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "system" in data
    assert "memory_percent" in data["system"]
    assert "cpu_percent" in data["system"]
    assert "resource_limit_percent" in data["system"]
    assert data["system"]["resource_limit_percent"] == 75.0
    assert "circuit_breakers" in data


def test_buffered_events_endpoint(admin_token):
    client = TestClient(app)
    response = client.get(
        "/metrics/events?channel=all&limit=20",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "channel" in data
    assert "events" in data
    assert isinstance(data["events"], list)
