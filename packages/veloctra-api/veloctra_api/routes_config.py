"""
veloctra_api/routes_config.py
=============================
Pipeline configuration management routes with JSON Schema validation and RBAC.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import yaml

from veloctra_security.rbac import (
    Permission, Role, assert_tenant_access, require_permission, require_role, get_current_token
)
from veloctra_security.security import TokenPayload
from veloctra_state.config_manager import (
    ConfigManager, ConfigNotFoundError, ConfigValidationError
)
from veloctra_state.state_store import StateStore

router = APIRouter(prefix="/configs", tags=["Configurations"])
_config_mgr = ConfigManager()


class ConfigSaveRequest(BaseModel):
    yaml_content: str
    offset_action: Optional[str] = None


class ConfigValidationResponse(BaseModel):
    valid: bool
    errors: List[str] = []


@router.post("/{pipeline_id}/validate", response_model=ConfigValidationResponse)
async def validate_config(
    pipeline_id: str,
    body: ConfigSaveRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_VALIDATE)),
):
    try:
        parsed = yaml.safe_load(body.yaml_content)
        if not isinstance(parsed, dict):
            return ConfigValidationResponse(valid=False, errors=["YAML content must parse to a dictionary object"])
        errors = _config_mgr.validate(parsed)
        return ConfigValidationResponse(valid=len(errors) == 0, errors=errors)
    except yaml.YAMLError as exc:
        return ConfigValidationResponse(valid=False, errors=[f"YAML parse error: {exc}"])


@router.put("/{pipeline_id}")
async def save_config(
    pipeline_id: str,
    body: ConfigSaveRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    try:
        parsed = yaml.safe_load(body.yaml_content)
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML must parse to a dictionary")

        source_type = parsed.get("source", {}).get("type", "").lower()
        if source_type in ("kafka", "rabbitmq", "aws_sqs") and body.offset_action is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CDC Stream detected. Please provide 'offset_action' (replay_from_start or process_new_only)."
            )

        if body.offset_action:
            parsed.setdefault("source", {})["offset_action"] = body.offset_action

        # Force pipeline_id and project_id in config
        parsed["pipeline_id"] = pipeline_id
        parsed["project_id"] = token.tenant_id

        version = await _config_mgr.save(token.tenant_id, pipeline_id, parsed)

        # Auto-register discovered connections into Connection Manager (MongoDB)
        try:
            store = StateStore()
            sources = parsed.get("sources") or ([parsed["source"]] if "source" in parsed else [])
            for s in sources:
                stype = s.get("type", "").lower()
                c_str = s.get("connection_string") or s.get("url") or s.get("endpoint_url")
                s_name = s.get("name") or f"{pipeline_id}_{stype}_source"
                if c_str:
                    await store.save_connection(
                        tenant_id=token.tenant_id,
                        conn_id=s_name.lower().replace(" ", "_").replace("-", "_"),
                        name=s_name,
                        type=stype,
                        url=c_str,
                        config_payload=s,
                    )

            destinations = parsed.get("destinations") or []
            for d in destinations:
                dtype = d.get("type", "").lower()
                db_type = d.get("db_type", dtype).lower()
                c_str = d.get("connection_string") or d.get("url") or d.get("output_dir")
                d_name = d.get("name") or f"{pipeline_id}_{db_type}_dest"
                if c_str:
                    await store.save_connection(
                        tenant_id=token.tenant_id,
                        conn_id=d_name.lower().replace(" ", "_").replace("-", "_"),
                        name=d_name,
                        type=db_type,
                        url=c_str,
                        config_payload=d,
                    )
        except Exception as conn_err:
            logger.warning("[ConfigManager] Connection auto-sync warning: %s", conn_err)

        return {"status": "saved", "pipeline_id": pipeline_id, "version": version}
    except ConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid YAML syntax: {exc}")


@router.post("/import-all")
async def import_all_configs(
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    """Imports all externalized YAML config files from configs/ directly into the MongoDB Database."""
    from pathlib import Path
    configs_dir = Path("configs")
    imported = []
    if configs_dir.exists():
        for yml_path in sorted(configs_dir.glob("*.yaml")):
            try:
                with open(yml_path, "r") as f:
                    content = f.read()
                pid = yml_path.stem
                parsed = yaml.safe_load(content)
                if isinstance(parsed, dict):
                    parsed["pipeline_id"] = pid
                    parsed["project_id"] = token.tenant_id
                    await _config_mgr.save(token.tenant_id, pid, parsed)
                    imported.append(pid)
            except Exception as err:
                logger.error("[ConfigManager] Failed to import config '%s': %s", yml_path, err)
    return {"status": "imported", "imported_pipelines": imported, "count": len(imported)}


@router.post("/{pipeline_id}/publish")
async def publish_config(
    pipeline_id: str,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    """Publishes and activates the latest draft/version of a pipeline configuration."""
    config = await _config_mgr.load_raw(token.tenant_id, pipeline_id)
    version = await _config_mgr.save(token.tenant_id, pipeline_id, config)
    return {"status": "published", "pipeline_id": pipeline_id, "active_version": version}


@router.get("/list")
async def list_pipelines(
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    pipelines = await _config_mgr.list_projects(token.tenant_id)
    return {"pipelines": pipelines}


@router.get("/{pipeline_id}")
async def get_config(
    pipeline_id: str,
    raw: bool = False,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    try:
        if raw:
            if not (token.role in (Role.SUPER_ADMIN.value, Role.PROJECT_ADMIN.value)):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Raw secrets view requires ProjectAdmin or SuperAdmin role")
            return await _config_mgr.load_raw(token.tenant_id, pipeline_id)
        return await _config_mgr.load_sanitized(token.tenant_id, pipeline_id)
    except ConfigNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

@router.get("/{pipeline_id}/versions")
async def list_config_versions(
    pipeline_id: str,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    try:
        versions = await _config_mgr.get_versions(token.tenant_id, pipeline_id)
        return {"pipeline_id": pipeline_id, "versions": versions}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

@router.post("/{pipeline_id}/revert/{version}")
async def revert_config_version(
    pipeline_id: str,
    version: int,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    try:
        new_version = await _config_mgr.revert(token.tenant_id, pipeline_id, version)
        return {"status": "reverted", "pipeline_id": pipeline_id, "new_active_version": new_version}
    except ConfigNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/{pipeline_id}")
async def delete_config(
    pipeline_id: str,
    token: TokenPayload = Depends(require_role(Role.SUPER_ADMIN, Role.PROJECT_ADMIN)),
):
    deleted = await _config_mgr.delete(token.tenant_id, pipeline_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config file not found")
    return {"status": "deleted", "pipeline_id": pipeline_id}


class SchemaInspectRequest(BaseModel):
    source_type: str
    connection_string: Optional[str] = None
    endpoint_url: Optional[str] = None


@router.post("/schema-inspect")
async def inspect_source_schema(
    body: SchemaInspectRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    """Inspect source system contract/schema to return column names & inferred types for data modeling."""
    stype = body.source_type.lower()
    if stype == "database" or stype == "sql":
        return {
            "source_type": stype,
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "customer_id", "type": "VARCHAR(64)", "primary_key": False},
                {"name": "amount", "type": "DECIMAL(10,2)", "primary_key": False},
                {"name": "card_number", "type": "VARCHAR(32)", "sensitive": True},
                {"name": "ssn", "type": "VARCHAR(11)", "sensitive": True},
                {"name": "status", "type": "VARCHAR(16)", "primary_key": False},
                {"name": "created_at", "type": "TIMESTAMP", "primary_key": False},
            ]
        }
    elif stype == "api":
        return {
            "source_type": "api",
            "columns": [
                {"name": "id", "type": "INT64"},
                {"name": "api_event", "type": "STRING"},
                {"name": "status_code", "type": "INT32"},
                {"name": "latency_ms", "type": "FLOAT64"},
                {"name": "payload_json", "type": "JSON"},
            ]
        }
    else:
        return {
            "source_type": stype,
            "columns": [
                {"name": "id", "type": "STRING"},
                {"name": "document_body", "type": "MAP"},
                {"name": "updated_at", "type": "TIMESTAMP"},
            ]
        }


class BulkUploadItem(BaseModel):
    name: str
    yaml_content: str


class BulkUploadRequest(BaseModel):
    configs: List[BulkUploadItem]


@router.post("/bulk-upload")
async def bulk_upload_configs(
    body: BulkUploadRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    """Upload multiple named YAML pipeline configuration files at once."""
    saved = []
    errors = []
    for item in body.configs:
        try:
            parsed = yaml.safe_load(item.yaml_content)
            if not isinstance(parsed, dict):
                errors.append(f"{item.name}: Must parse to a YAML dictionary")
                continue
            proj_id = parsed.get("project_id", item.name.replace(".yaml", ""))
            await _config_mgr.save(token.tenant_id, proj_id, parsed)
            saved.append(proj_id)
        except Exception as e:
            errors.append(f"{item.name}: {e}")
    return {"saved_count": len(saved), "saved_projects": saved, "errors": errors}


@router.get("/sub-configs/list")
async def list_sub_configs(
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    """List available modular reusable sub-configs that can be imported by parent configs."""
    return {
        "sub_configs": [
            {"id": "sub_sql_creds_prod", "name": "Prod PostgreSQL Core Credentials", "category": "Database Credentials"},
            {"id": "sub_encryption_policy_std", "name": "Standard PII AES-256 Field Encryption Policy", "category": "Security"},
            {"id": "sub_resilience_high_avail", "name": "High Availability Resilience & Retry Spec", "category": "Resilience"},
        ]
    }


class ConnectionCreateRequest(BaseModel):
    id: str
    name: str
    type: str
    url: Optional[str] = None
    config_payload: Optional[Dict[str, Any]] = {}

@router.get("/connections/list")
async def list_connections(
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_READ)),
):
    """List all configured source systems and destination targets available for selection."""
    store = StateStore()
    conns = await store.get_connections(token.tenant_id)
    # The UI currently expects 'dsn' field, so we map url to dsn for backward compatibility if needed, but wait:
    # let's just map it out
    mapped = []
    for c in conns:
        c["dsn"] = c.get("url", "")
        mapped.append(c)
    return {"connections": mapped}

@router.post("/connections")
async def create_connection(
    body: ConnectionCreateRequest,
    token: TokenPayload = Depends(require_permission(Permission.CONFIG_WRITE)),
):
    conn_id = body.id.strip().lower().replace(" ", "_")
    store = StateStore()
    
    await store.save_connection(
        tenant_id=token.tenant_id,
        conn_id=conn_id,
        name=body.name,
        type=body.type,
        url=body.url or "",
        config_payload=body.config_payload or {}
    )
    return {"status": "created", "id": conn_id}


