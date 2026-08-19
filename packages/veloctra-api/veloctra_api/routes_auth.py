"""
veloctra_api/routes_auth.py
===========================
Authentication REST API routes.
"""

from __future__ import annotations

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from veloctra_security.rbac import Role, require_role, get_current_token
from veloctra_security.security import (
    TokenPayload,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

_DEMO_USERS: Dict[str, Dict] = {
    "admin": {
        "password_hash": hash_password("changeme"),
        "role": Role.SUPER_ADMIN.value,
        "tenant_id": "finance_prod_workspace",
    },
    "developer": {
        "password_hash": hash_password("devpass"),
        "role": Role.DEVELOPER.value,
        "tenant_id": "finance_prod_workspace",
    },
}


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    user = _DEMO_USERS.get(body.username)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(
        subject=body.username,
        role=user["role"],
        tenant_id=user["tenant_id"],
    )

    return LoginResponse(
        access_token=token,
        role=user["role"],
        tenant_id=user["tenant_id"],
    )


@router.get("/me")
async def get_me(token: TokenPayload = Depends(get_current_token)):
    return {
        "username": token.sub,
        "role": token.role,
        "tenant_id": token.tenant_id,
        "exp": token.exp,
    }
