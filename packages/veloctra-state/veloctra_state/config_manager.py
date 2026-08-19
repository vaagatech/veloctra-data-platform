"""
veloctra_state/config_manager.py
================================
JSON Schema-validated YAML pipeline configuration manager with secret sanitisation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncio
import jsonschema
import yaml
from veloctra_state.state_store import StateStore

from veloctra_security.security import sanitize_config

logger = logging.getLogger(__name__)

PIPELINE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["project_id", "pipeline_id", "destinations"],
    "properties": {
        "project_id": {"type": "string", "minLength": 1},
        "pipeline_id": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "mode": {"type": "string", "enum": ["bulk", "delta"]},
        "resilience": {
            "type": "object",
            "properties": {
                "max_retries": {"type": "integer", "minimum": 0},
                "initial_backoff_seconds": {"type": "number", "minimum": 0},
                "max_backoff_seconds": {"type": "number", "minimum": 0},
                "circuit_breaker_failure_threshold": {"type": "integer", "minimum": 1},
                "circuit_breaker_cooldown_seconds": {"type": "number", "minimum": 1},
            },
        },
        "memory_limits": {
            "type": "object",
            "properties": {
                "max_batch_memory_mb": {"type": "integer", "minimum": 1},
                "force_gc_every_n_chunks": {"type": "integer", "minimum": 1},
            },
        },
        "security": {
            "type": "object",
            "properties": {
                "secrets_provider": {"type": "string", "enum": ["env", "vault", "aws_secrets"]},
                "field_encryption": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "kms_key_id": {"type": "string"},
                        "fields_to_encrypt": {"type": "array", "items": {"type": "string"}},
                        "fields_to_decrypt": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        "import_sub_configs": {
            "type": "array",
            "items": {"type": "string"}
        },
        "source": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"type": "string"},
                "connection_string": {"type": "string"},
                "endpoint_url": {"type": "string"},
                "method": {"type": "string"},
                "auth_token": {"type": "string"},
                "chunk_size": {"type": "integer", "minimum": 1},
            },
        },
        "sources": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {"type": "string"},
                    "connection_string": {"type": "string"},
                    "endpoint_url": {"type": "string"},
                    "method": {"type": "string"},
                    "auth_token": {"type": "string"},
                    "chunk_size": {"type": "integer", "minimum": 1},
                }
            }
        },

        "transformations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type"],
            },
        },
        "destinations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "type"],
            },
        },
    },
}


class ConfigValidationError(Exception):
    """Raised when a pipeline configuration fails JSON Schema validation."""


class ConfigNotFoundError(Exception):
    """Raised when a requested configuration file does not exist."""


class ConfigManager:
    def __init__(self):
        # ConfigManager now uses StateStore async
        pass

    def seed_sample_configs(self) -> None:
        # Seeding should be done externally or via a migration script now that we use SQLite
        pass

    def validate(self, config: Dict[str, Any]) -> List[str]:
        validator = jsonschema.Draft202012Validator(PIPELINE_SCHEMA)
        errors = []
        for error in validator.iter_errors(config):
            path_str = " -> ".join(str(p) for p in error.absolute_path) or "root"
            errors.append(f"[{path_str}] {error.message}")
        return errors

    async def save(self, tenant_id: str, project_id: str, config: Dict[str, Any]) -> int:
        errors = self.validate(config)
        if errors:
            raise ConfigValidationError(f"Configuration validation failed with {len(errors)} error(s):\n" + "\n".join(errors))

        store = StateStore()
        version = await store.save_pipeline_config(tenant_id, project_id, config)
        logger.info("[ConfigManager] Saved config for tenant '%s', project '%s', version %d", tenant_id, project_id, version)
        return version

    async def load_raw(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Dict[str, Any]:
        store = StateStore()
        config = await store.get_pipeline_config(tenant_id, project_id, version)
        if config:
            return config

        # Optional filesystem fallback for CI/CD external configs
        for candidate_path in (
            Path(f"configs/{project_id}.yaml"),
            Path(f"configs/{project_id}.yml"),
        ):
            if candidate_path.exists():
                try:
                    with open(candidate_path, "r") as f:
                        file_config = yaml.safe_load(f)
                    if isinstance(file_config, dict):
                        file_config.setdefault("project_id", project_id)
                        file_config.setdefault("pipeline_id", project_id)
                        # Auto-persist into StateStore
                        await store.save_pipeline_config(tenant_id, project_id, file_config)
                        return file_config
                except Exception as err:
                    logger.warning("[ConfigManager] Error reading file config '%s': %s", candidate_path, err)

        raise ConfigNotFoundError(f"Config not found for project '{project_id}' (tenant '{tenant_id}')")

    async def load_sanitized(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Dict[str, Any]:
        config = await self.load_raw(tenant_id, project_id, version)
        return sanitize_config(config)

    async def get_versions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        store = StateStore()
        return await store.get_pipeline_versions(tenant_id, project_id)

    async def revert(self, tenant_id: str, project_id: str, version: int) -> int:
        config = await self.load_raw(tenant_id, project_id, version)
        return await self.save(tenant_id, project_id, config)

    async def delete(self, tenant_id: str, project_id: str) -> bool:
        store = StateStore()
        deleted = await store.delete_pipeline_config(tenant_id, project_id)
        if deleted:
            logger.info("[ConfigManager] Deleted config '%s' for tenant '%s'", project_id, tenant_id)
        return deleted

    async def list_projects(self, tenant_id: str) -> List[str]:
        store = StateStore()
        configs = await store.get_pipeline_configs(tenant_id)
        projects_set = {c["project_id"] for c in configs}

        # Include configs from filesystem
        configs_dir = Path("configs")
        if configs_dir.exists():
            for p in configs_dir.glob("*.yaml"):
                projects_set.add(p.stem)

        return sorted(list(projects_set))

