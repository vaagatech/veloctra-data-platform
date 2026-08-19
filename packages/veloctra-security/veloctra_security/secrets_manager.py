"""
veloctra_security/secrets_manager.py
======================================
Multi-provider dynamic secrets resolver supporting env, Vault, and AWS Secrets Manager.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from veloctra_core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=128)
def resolve_secret(secret_ref: str) -> str:
    """
    Resolve *secret_ref* string.
    Syntaxes:
      - ``env:VAR_NAME``
      - ``vault:secret/path#key``
      - ``aws:secret-id#key``
      - Plain text string (returned unchanged).
    """
    if not isinstance(secret_ref, str):
        return secret_ref

    if not secret_ref.strip():
        return secret_ref

    if ":" not in secret_ref:
        return secret_ref

    provider, remainder = secret_ref.split(":", 1)
    provider = provider.strip().lower()

    if provider == "env":
        return _from_env(remainder)
    if provider == "vault":
        return _from_vault(remainder)
    if provider == "aws":
        return _from_aws(remainder)

    return secret_ref


def _from_env(var_name: str) -> str:
    val = os.environ.get(var_name)
    if val:
        return val

    # Fallback to settings attribute if set
    settings_val = getattr(settings, var_name.lower(), None)
    if settings_val:
        return str(settings_val)

    if var_name == "APP_ENCRYPTION_KEY":
        import base64
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["APP_ENCRYPTION_KEY"] = key
        return key

    raise ValueError(
        f"Environment variable '{var_name}' is not set. Check your .env file or container environment."
    )



def _from_vault(path_and_key: str) -> str:
    import hvac

    path, key = _split_path_and_key(path_and_key)
    client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)

    if not client.is_authenticated():
        raise RuntimeError(f"Vault client at '{settings.vault_addr}' failed authentication")

    secret = client.secrets.kv.v2.read_secret_version(path=path)
    data = secret["data"]["data"]

    if key not in data:
        raise KeyError(f"Key '{key}' not found in Vault secret path '{path}'")

    return data[key]


def _from_aws(path_and_key: str) -> str:
    import json
    import boto3

    secret_id, key = _split_path_and_key(path_and_key)
    client = boto3.client("secretsmanager", region_name=settings.aws_default_region)
    response = client.get_secret_value(SecretId=secret_id)

    raw_secret = response.get("SecretString", "")
    try:
        parsed = json.loads(raw_secret)
        if isinstance(parsed, dict) and key in parsed:
            return parsed[key]
    except json.JSONDecodeError:
        pass

    return raw_secret


def _split_path_and_key(ref: str) -> tuple[str, str]:
    if "#" in ref:
        path, key = ref.split("#", 1)
        return path.strip(), key.strip()
    return ref.strip(), "value"


def clear_secret_cache() -> None:
    resolve_secret.cache_clear()
