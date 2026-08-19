"""
veloctra_api/routes_rbac.py
============================
RBAC & Group-Based Access Control (GBAC) Users, Groups & Roles management endpoints.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from veloctra_security.rbac import Role, require_role
from veloctra_security.security import TokenPayload

router = APIRouter(prefix="/rbac", tags=["RBAC & Security"])

_USERS_DB = [
    {"id": "usr_01", "username": "admin", "role": "SuperAdmin", "group": "Global Platform Operations", "tenant_id": "* (Global Scope)", "status": "ACTIVE"},
    {"id": "usr_02", "username": "data_engineer_alex", "role": "Developer", "group": "Finance Data Engineering", "tenant_id": "finance_prod_workspace", "status": "ACTIVE"},
    {"id": "usr_03", "username": "ops_lead_sarah", "role": "Operator", "group": "Marketing Analytics Group", "tenant_id": "marketing_analytics_workspace", "status": "ACTIVE"},
    {"id": "usr_04", "username": "auditor_james", "role": "Viewer", "group": "Global Compliance & Audit", "tenant_id": "* (Global Scope)", "status": "ACTIVE"},
]

_GROUPS_DB = [
    {"id": "grp_finance", "name": "Finance Data Engineering", "default_role": "Developer", "default_workspace": "finance_prod_workspace", "members_count": 5},
    {"id": "grp_marketing", "name": "Marketing Analytics Group", "default_role": "Operator", "default_workspace": "marketing_analytics_workspace", "members_count": 3},
    {"id": "grp_platform_ops", "name": "Global Platform Operations", "default_role": "SuperAdmin", "default_workspace": "* (Global Scope)", "members_count": 2},
    {"id": "grp_compliance", "name": "Global Compliance & Audit", "default_role": "Viewer", "default_workspace": "* (Global Scope)", "members_count": 4},
]

_ROLES_PERMISSIONS = {
    "SuperAdmin": ["* (All Platform Resources)"],
    "PlatformAdmin": ["config:read", "config:write", "config:delete", "pipeline:start", "pipeline:pause", "pipeline:resume", "dlq:replay", "audit:view", "rbac:manage"],
    "ProjectAdmin": ["config:read", "config:write", "config:delete", "pipeline:start", "pipeline:pause", "pipeline:resume", "dlq:replay", "audit:view"],
    "Developer": ["config:read", "config:write", "config:validate", "pipeline:start", "pipeline:pause", "pipeline:resume"],
    "Operator": ["config:read", "pipeline:start", "pipeline:pause", "pipeline:resume", "dlq:replay", "audit:view"],
    "Viewer": ["config:read", "audit:view"],
}


class UserCreateRequest(BaseModel):
    username: str
    role: str
    group: Optional[str] = "Finance Data Engineering"
    tenant_id: str


class GroupCreateRequest(BaseModel):
    name: str
    default_role: str
    default_workspace: str


@router.get("/users")
async def list_users(
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN)),
):
    return {"users": _USERS_DB}


@router.post("/users")
async def create_user(
    body: UserCreateRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN)),
):
    new_user = {
        "id": f"usr_{len(_USERS_DB) + 1:02d}",
        "username": body.username,
        "role": body.role,
        "group": body.group or "General Engineering",
        "tenant_id": body.tenant_id,
        "status": "ACTIVE",
    }
    _USERS_DB.append(new_user)
    return {"status": "created", "user": new_user}


@router.get("/groups")
async def list_groups(
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER)),
):
    return {"groups": _GROUPS_DB}


@router.post("/groups")
async def create_group(
    body: GroupCreateRequest,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN)),
):
    new_group = {
        "id": f"grp_{len(_GROUPS_DB) + 1:02d}",
        "name": body.name,
        "default_role": body.default_role,
        "default_workspace": body.default_workspace,
        "members_count": 1,
    }
    _GROUPS_DB.append(new_group)
    return {"status": "created", "group": new_group}


@router.get("/roles")
async def list_roles(
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN, Role.DEVELOPER)),
):
    return {"roles": _ROLES_PERMISSIONS}
