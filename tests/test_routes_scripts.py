"""
tests/test_routes_scripts.py
============================
Tests for /scripts/validate REST endpoint.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from veloctra_api.main import app
from veloctra_security.security import create_access_token
from veloctra_security.rbac import Role


@pytest.mark.asyncio
async def test_validate_script_success():
    token = create_access_token(subject="dev_user", role=Role.DEVELOPER.value, tenant_id="tenant_scripts")
    headers = {"Authorization": f"Bearer {token}"}

    valid_script = """
def transform_df(df):
    df["tax"] = df["amount"] * 0.08
    return df
"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "script_code": valid_script,
            "entrypoint": "transform_df",
            "sample_records": [
                {"id": 1, "amount": 100.0},
                {"id": 2, "amount": 250.0},
            ]
        }
        res = await client.post("/scripts/validate", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["flavor"] == "pandas"
        assert len(data["sample_output"]) == 2
        assert data["sample_output"][0]["tax"] == 8.0


@pytest.mark.asyncio
async def test_validate_script_syntax_error():
    token = create_access_token(subject="dev_user", role=Role.DEVELOPER.value, tenant_id="tenant_scripts")
    headers = {"Authorization": f"Bearer {token}"}

    broken_script = "def transform(batch: syntax_error_here"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"script_code": broken_script}
        res = await client.post("/scripts/validate", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is False
        assert data["error"] is not None
