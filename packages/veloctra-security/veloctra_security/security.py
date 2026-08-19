"""
veloctra_security/security.py
==============================
Direct bcrypt password hashing, JWT lifecycle management, and recursive secret scrubbing.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Dict, Optional

import bcrypt
import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from veloctra_core.settings import get_settings

settings = get_settings()


# ── Password Hashing ────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    pwd_bytes = plain.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verify *plain* against stored *hashed* password."""
    try:
        pwd_bytes = plain.encode('utf-8')[:72]
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


# ── JWT ─────────────────────────────────────────────────────────────────────────

class TokenPayload:
    """Decoded, validated JWT payload."""

    def __init__(self, sub: str, role: str, tenant_id: str, exp: int):
        self.sub = sub
        self.role = role
        self.tenant_id = tenant_id
        self.exp = exp


def create_access_token(
    subject: str,
    role: str,
    tenant_id: str,
    expires_in_minutes: Optional[int] = None,
) -> str:
    """Create a signed JWT access token."""
    expire_minutes = expires_in_minutes or settings.jwt_expire_minutes
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expire_minutes * 60,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "role", "tenant_id"]},
    )
    return TokenPayload(
        sub=payload["sub"],
        role=payload["role"],
        tenant_id=payload["tenant_id"],
        exp=payload["exp"],
    )


# ── Secret Scrubbing ────────────────────────────────────────────────────────────

_SECRET_PATTERN = re.compile(
    r"|".join(re.escape(p) for p in settings.secret_field_patterns),
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def sanitize_value(key: str, value: Any) -> Any:
    """Return *_REDACTED* if *key* matches any secret pattern, else *value*."""
    if isinstance(key, str) and _SECRET_PATTERN.search(key):
        return _REDACTED
    return value


def sanitize_config(data: Any) -> Any:
    """Recursively scrub secret-matching keys from *data*."""
    if isinstance(data, dict):
        return {k: sanitize_config(sanitize_value(k, v)) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_config(item) for item in data]
    return data

# ── Double Envelope Encryption & Key Rotation ──────────────────────────────────

import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


class KeyRotationManager:
    """Manages versioned primary and secondary encryption keys for dynamic zero-downtime key rotation."""

    _instance: Optional["KeyRotationManager"] = None

    def __init__(self):
        self._key_versions: Dict[int, Dict[str, bytes]] = {}
        self._active_version: int = 1
        self._init_default_keys()

    def _init_default_keys(self) -> None:
        jwt_sec = settings.jwt_secret_key
        # Primary key derivation (Fernet / AES-256)
        m1 = hashlib.sha256(jwt_sec.encode("utf-8") + b":primary")
        primary_k = base64.urlsafe_b64encode(m1.digest())

        # Secondary key derivation (ChaCha20-Poly1305 32-byte key)
        m2 = hashlib.sha256(jwt_sec.encode("utf-8") + b":secondary_chacha20")
        secondary_k = m2.digest()

        self._key_versions[1] = {
            "primary": primary_k,
            "secondary": secondary_k,
        }

    @classmethod
    def get_instance(cls) -> "KeyRotationManager":
        if cls._instance is None:
            cls._instance = KeyRotationManager()
        return cls._instance

    @property
    def active_version(self) -> int:
        return self._active_version

    def add_key_version(self, version: int, primary_key: bytes, secondary_key: bytes) -> None:
        self._key_versions[version] = {
            "primary": primary_key,
            "secondary": secondary_key,
        }
        if version > self._active_version:
            self._active_version = version

    def get_keys(self, version: int) -> Dict[str, bytes]:
        if version not in self._key_versions:
            raise ValueError(f"Unknown encryption key version: {version}")
        return self._key_versions[version]

    def rotate_keys(self, new_primary_seed: Optional[str] = None, new_secondary_seed: Optional[str] = None) -> int:
        """Dynamically rotates encryption keys to next version."""
        new_version = self._active_version + 1
        p_seed = (new_primary_seed or os.urandom(32).hex()).encode("utf-8")
        s_seed = (new_secondary_seed or os.urandom(32).hex()).encode("utf-8")

        p_key = base64.urlsafe_b64encode(hashlib.sha256(p_seed).digest())
        s_key = hashlib.sha256(s_seed).digest()

        self.add_key_version(new_version, p_key, s_key)
        return new_version


class DoubleEncryptionService:
    """
    Enterprise Double Envelope Encryption Service:
    - Layer 1: AES-128-CBC + HMAC (Fernet) with primary rotating key.
    - Layer 2: ChaCha20-Poly1305 Authenticated Encryption with secondary rotating key.
    - Tagged with dynamic key version metadata for seamless zero-downtime key rotation.
    """

    def __init__(self, key_rotation_mgr: Optional[KeyRotationManager] = None):
        self.rotation_mgr = key_rotation_mgr or KeyRotationManager.get_instance()

    def encrypt_string(self, text: str, tenant_id: str = "default") -> str:
        if not text:
            return text

        active_ver = self.rotation_mgr.active_version
        keys = self.rotation_mgr.get_keys(active_ver)

        # Layer 1: Fernet / AES
        f = Fernet(keys["primary"])
        layer1_bytes = f.encrypt(text.encode("utf-8"))

        # Layer 2: ChaCha20-Poly1305 AEAD with tenant aad context
        chacha = ChaCha20Poly1305(keys["secondary"])
        nonce = os.urandom(12)
        aad = f"veloctra:{tenant_id}:v{active_ver}".encode("utf-8")
        layer2_bytes = chacha.encrypt(nonce, layer1_bytes, aad)

        # Payload: v{version}:{nonce_b64}:{ciphertext_b64}
        nonce_b64 = base64.b64encode(nonce).decode("utf-8")
        ct_b64 = base64.b64encode(layer2_bytes).decode("utf-8")
        return f"enc:v{active_ver}:{nonce_b64}:{ct_b64}"

    def decrypt_string(self, token: str, tenant_id: str = "default") -> str:
        if not token:
            return token

        # Handle Double Encrypted tokens
        if token.startswith("enc:v"):
            parts = token.split(":", 3)
            if len(parts) == 4:
                ver_str, nonce_b64, ct_b64 = parts[1], parts[2], parts[3]
                version = int(ver_str.replace("v", ""))
                keys = self.rotation_mgr.get_keys(version)

                nonce = base64.b64decode(nonce_b64)
                ciphertext = base64.b64decode(ct_b64)
                aad = f"veloctra:{tenant_id}:v{version}".encode("utf-8")

                # Layer 2 Decrypt (ChaCha20Poly1305)
                chacha = ChaCha20Poly1305(keys["secondary"])
                layer1_bytes = chacha.decrypt(nonce, ciphertext, aad)

                # Layer 1 Decrypt (Fernet)
                f = Fernet(keys["primary"])
                plain_bytes = f.decrypt(layer1_bytes)
                return plain_bytes.decode("utf-8")

        # Fallback for legacy single-encrypted tokens
        try:
            keys = self.rotation_mgr.get_keys(1)
            f = Fernet(keys["primary"])
            return f.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception:
            return token

    def encrypt_dict(self, data: Dict[str, Any], tenant_id: str = "default") -> str:
        json_bytes = json.dumps(data)
        return self.encrypt_string(json_bytes, tenant_id=tenant_id)

    def decrypt_dict(self, token: str, tenant_id: str = "default") -> Dict[str, Any]:
        raw_json = self.decrypt_string(token, tenant_id=tenant_id)
        return json.loads(raw_json)


class EncryptionService(DoubleEncryptionService):
    """Backward-compatible facade delegating to DoubleEncryptionService."""
    pass
