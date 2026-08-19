"""
veloctra_api/routes_projects.py
===============================
Project workspace management endpoints.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from veloctra_security.rbac import Permission, require_permission, get_current_token
from veloctra_security.security import TokenPayload
from veloctra_state.state_store import StateStore

router = APIRouter(prefix="/projects", tags=["Projects"])

class ProjectCreateRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""

@router.get("")
async def list_projects(
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    store = StateStore()
    projects = await store.get_projects(token.tenant_id)
    return {"projects": projects}

@router.post("")
async def create_project(
    body: ProjectCreateRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    proj_id = body.id.strip().lower().replace(" ", "_")
    store = StateStore()
    
    existing = await store.get_projects(token.tenant_id)
    for p in existing:
        if p["id"] == proj_id:
            raise HTTPException(status_code=400, detail="Project with this ID already exists")

    await store.save_project(token.tenant_id, proj_id, body.name, body.description)
    new_proj = {"id": proj_id, "name": body.name, "description": body.description}
    return {"status": "created", "project": new_proj}
