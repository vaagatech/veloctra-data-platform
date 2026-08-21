"""
tests/test_keda_sizing_api.py
=============================
Tests for /pipelines/{pipeline_id}/estimate-size endpoint and KEDA scaling API.
"""

import os
import sqlite3
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
from veloctra_api.main import app
from veloctra_security.rbac import Role
from veloctra_security.security import create_access_token
from veloctra_state.state_store import StateStore


@pytest.fixture
def test_setup():
    fd, path = tempfile.mkstemp(suffix="_api_sizing.db")
    os.close(fd)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        for i in range(1, 15001):
            conn.execute(f"INSERT INTO users VALUES ({i}, 'User {i}')")
        conn.commit()

    token = create_access_token(
        subject="data_eng",
        role=Role.DEVELOPER.value,
        tenant_id="tenant_keda",
    )
    headers = {"Authorization": f"Bearer {token}"}

    yield path, headers

    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_estimate_pipeline_size_endpoint(test_setup):
    db_path, headers = test_setup
    store = StateStore()

    config = {
        "project_id": "keda_user_migration",
        "pipeline_id": "keda_user_migration",
        "tenant_id": "tenant_keda",
        "settings": {
            "keda": {
                "rows_per_worker": 5000,
                "min_replicas": 1,
                "max_replicas": 8,
            }
        },
        "sources": [
            {
                "name": "sqlite_users",
                "type": "database",
                "connection_string": f"sqlite:///{db_path}",
                "query": "SELECT * FROM users",
            }
        ],
        "destinations": [
            {
                "name": "dummy_dest",
                "type": "file",
                "path": "/tmp/out.csv",
            }
        ],
    }

    await store.save_pipeline_config("tenant_keda", "keda_user_migration", config)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/pipelines/keda_user_migration/estimate-size", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_id"] == "keda_user_migration"
        assert data["total_rows"] == 15000
        assert data["recommended_replicas"] == 3  # ceil(15000 / 5000) = 3
        assert data["recommended_shards"] >= 3
        assert len(data["shard_intervals"]) >= 3
        assert data["keda_enabled"] is True
