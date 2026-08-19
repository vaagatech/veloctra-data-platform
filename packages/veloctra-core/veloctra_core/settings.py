"""
veloctra_core/settings.py
========================
Centralised, validated configuration for Veloctra Data Platform.
Sourced from environment variables (12-factor).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── JWT / Server ───────────────────────────────────────────────────────────
    jwt_secret_key: str = "changeme-replace-with-a-64-char-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ── Encryption ─────────────────────────────────────────────────────────────
    # 32-byte key, base64-encoded
    app_encryption_key: str = ""
    secondary_encryption_key: str = ""

    # ── Database URIs ──────────────────────────────────────────────────────────
    prod_source_db_uri: str = ""
    prod_target_db_uri: str = ""
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_system_db: str = "veloctra_system"

    # ── AWS ────────────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"

    # ── HashiCorp Vault ────────────────────────────────────────────────────────
    vault_addr: str = "http://127.0.0.1:8200"
    vault_token: str = ""

    # ── State / Persistence ────────────────────────────────────────────────────
    state_store_type: str = "mongodb"
    state_db_path: str = "./state.db"

    # ── Memory & Processing Limits ─────────────────────────────────────────────
    max_memory_percent: float = 75.0
    """RAM usage % above which backpressure kicks in (leaving >= 25% for GC)."""
    max_cpu_percent: float = 75.0
    """CPU usage % above which backpressure kicks in (leaving >= 25% for GC)."""
    critical_memory_percent: float = 85.0
    """RAM/CPU usage % above which processing is paused aggressively."""
    default_chunk_size: int = 10_000
    """Default number of rows per processing chunk."""
    min_chunk_size: int = 1
    """Minimum chunk size when adaptive backpressure or huge records are detected."""

    # ── API / Server ───────────────────────────────────────────────────────────
    cors_origins: Union[List[str], str] = ["http://localhost:5173", "http://localhost:8000", "http://localhost:3000"]
    log_level: str = "INFO"
    debug: bool = False

    # ── Security header defaults ───────────────────────────────────────────────
    # Fields whose values are scrubbed in logs / API responses
    secret_field_patterns: List[str] = [
        "password", "secret", "token", "key", "credential",
        "auth", "private", "passwd", "pwd",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("max_memory_percent")
    @classmethod
    def validate_memory_percent(cls, v):
        if not (40.0 <= v <= 99.0):
            raise ValueError("max_memory_percent must be between 40 and 99")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
