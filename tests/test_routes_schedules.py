"""
tests/test_routes_schedules.py
==============================
Tests for schedule creation, listing, and deletion API endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from veloctra_api.main import app
from veloctra_security.security import create_access_token
from veloctra_security.rbac import Role


@pytest.mark.asyncio
async def test_schedule_crud_endpoints():
    token = create_access_token(subject="user_admin", role=Role.SUPER_ADMIN.value, tenant_id="tenant_sched")
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create schedule
        create_payload = {
            "schedule_id": "test_cron_1",
            "pipeline_id": "claims_sync_pipeline",
            "interval_seconds": 60,
            "enabled": True,
        }
        res = await client.post("/schedules", json=create_payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "created"

        # 2. List schedules
        res_list = await client.get("/schedules", headers=headers)
        assert res_list.status_code == 200
        schedules = res_list.json()
        assert len(schedules) >= 1
        assert any(s["schedule_id"] == "test_cron_1" for s in schedules)

        # 3. Delete schedule
        res_del = await client.delete("/schedules/test_cron_1", headers=headers)
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"
