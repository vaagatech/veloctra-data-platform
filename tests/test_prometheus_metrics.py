"""
tests/test_prometheus_metrics.py
================================
Tests for the Prometheus /metrics exporter endpoint.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from veloctra_api.main import app


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
