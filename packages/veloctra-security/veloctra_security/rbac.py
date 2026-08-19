"""
veloctra_security/rbac.py
========================
Role-Based Access Control with project/tenant isolation.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import FrozenSet, Set

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from veloctra_security.security import TokenPayload, decode_access_token


class Role(str, Enum):
    SUPER_ADMIN = "SuperAdmin"
    PROJECT_ADMIN = "ProjectAdmin"
    DEVELOPER = "Developer"
    OPERATOR = "Operator"
    VIEWER = "Viewer"


class Permission(str, Enum):
    PIPELINE_START = "pipeline:start"
    PIPELINE_PAUSE = "pipeline:pause"
    PIPELINE_RESUME = "pipeline:resume"
    PIPELINE_VIEW = "pipeline:view"

    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    CONFIG_VALIDATE = "config:validate"
    CONFIG_SECRETS_VIEW = "config:secrets:view"

    DLQ_VIEW = "dlq:view"
    DLQ_REPLAY = "dlq:replay"

    USER_CREATE = "user:create"
    USER_VIEW = "user:view"

    AUDIT_VIEW = "audit:view"


_ROLE_PERMISSIONS: dict[Role, FrozenSet[Permission]] = {
    Role.SUPER_ADMIN: frozenset(Permission),

    Role.PROJECT_ADMIN: frozenset({
        Permission.PIPELINE_START, Permission.PIPELINE_PAUSE,
        Permission.PIPELINE_RESUME, Permission.PIPELINE_VIEW,
        Permission.CONFIG_READ, Permission.CONFIG_WRITE,
        Permission.CONFIG_VALIDATE, Permission.CONFIG_SECRETS_VIEW,
        Permission.DLQ_VIEW, Permission.DLQ_REPLAY,
        Permission.USER_VIEW, Permission.AUDIT_VIEW,
    }),

    Role.DEVELOPER: frozenset({
        Permission.PIPELINE_START, Permission.PIPELINE_RESUME,
        Permission.PIPELINE_VIEW,
        Permission.CONFIG_READ, Permission.CONFIG_WRITE,
        Permission.CONFIG_VALIDATE,
        Permission.DLQ_VIEW, Permission.DLQ_REPLAY,
        Permission.AUDIT_VIEW,
    }),

    Role.OPERATOR: frozenset({
        Permission.PIPELINE_PAUSE, Permission.PIPELINE_RESUME,
        Permission.PIPELINE_VIEW,
        Permission.CONFIG_READ,
        Permission.DLQ_VIEW, Permission.DLQ_REPLAY,
        Permission.AUDIT_VIEW,
    }),

    Role.VIEWER: frozenset({
        Permission.PIPELINE_VIEW,
        Permission.CONFIG_READ,
        Permission.DLQ_VIEW,
        Permission.AUDIT_VIEW,
    }),
}


@lru_cache(maxsize=None)
def get_permissions(role: Role) -> FrozenSet[Permission]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in get_permissions(role)


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> TokenPayload:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*required_roles: Role):
    async def _check(token: TokenPayload = Depends(get_current_token)) -> TokenPayload:
        if token.role not in {r.value for r in required_roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token.role}' is not allowed. Required: {[r.value for r in required_roles]}",
            )
        return token
    return _check


def require_permission(permission: Permission):
    async def _check(token: TokenPayload = Depends(get_current_token)) -> TokenPayload:
        try:
            role = Role(token.role)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unknown role")
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' required",
            )
        return token
    return _check


def assert_tenant_access(token: TokenPayload, project_id: str) -> None:
    if token.role == Role.SUPER_ADMIN.value:
        return
    if token.tenant_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this project is not permitted for your tenant",
        )
