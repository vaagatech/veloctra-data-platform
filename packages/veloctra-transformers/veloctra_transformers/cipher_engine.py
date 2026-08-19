"""
veloctra_transformers/cipher_engine.py
=======================================
AES-256-GCM field-level encryption/decryption for PyArrow RecordBatches.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import pyarrow as pa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from veloctra_security.secrets_manager import resolve_secret


class CipherEngine:
    def __init__(self, key_ref: str):
        self._key_ref = key_ref
        self._aesgcm: Optional[AESGCM] = None

    def _get_key(self) -> bytes:
        raw = resolve_secret(self._key_ref)
        if raw.startswith("plain-"):
            raw = raw[6:]
        try:
            # Fix base64 padding if needed
            padded = raw + "=" * (-len(raw) % 4)
            return base64.urlsafe_b64decode(padded)
        except Exception:
            return raw.encode("utf-8")[:32].ljust(32, b"\0")


    def _get_cipher(self) -> AESGCM:
        if self._aesgcm is None:
            key_bytes = self._get_key()
            if len(key_bytes) != 32:
                raise ValueError(f"AES-256-GCM key must be 32 bytes (got {len(key_bytes)})")
            self._aesgcm = AESGCM(key_bytes)
        return self._aesgcm

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            return None
        cipher = self._get_cipher()
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, str(plaintext).encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        if ciphertext is None:
            return None
        cipher = self._get_cipher()
        raw = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        nonce = raw[:12]
        payload = raw[12:]
        decrypted_bytes = cipher.decrypt(nonce, payload, None)
        return decrypted_bytes.decode("utf-8")

    def encrypt_column(self, values: Any) -> List[Optional[str]]:
        py_vals = [v.as_py() if hasattr(v, "as_py") else v for v in values]
        return [self.encrypt(v) if v is not None else None for v in py_vals]

    def decrypt_column(self, values: Any) -> List[Optional[str]]:
        py_vals = [v.as_py() if hasattr(v, "as_py") else v for v in values]
        return [self.decrypt(v) if v is not None else None for v in py_vals]


    def encrypt_batch_fields(self, batch: pa.RecordBatch, fields: List[str]) -> pa.RecordBatch:
        if not fields or batch.num_rows == 0:
            return batch

        new_columns = []
        new_fields = []
        for f, col in zip(batch.schema, batch.columns):
            if f.name in fields:
                vals = [col[i].as_py() for i in range(batch.num_rows)]
                encrypted_vals = self.encrypt_column(vals)
                new_columns.append(pa.array(encrypted_vals, type=pa.string()))
                new_fields.append(pa.field(f.name, pa.string(), nullable=True))
            else:
                new_columns.append(col)
                new_fields.append(f)

        new_schema = pa.schema(new_fields)
        return pa.RecordBatch.from_arrays(new_columns, schema=new_schema)

    def decrypt_batch_fields(self, batch: pa.RecordBatch, fields: List[str]) -> pa.RecordBatch:
        if not fields or batch.num_rows == 0:
            return batch

        new_columns = []
        new_fields = []
        for f, col in zip(batch.schema, batch.columns):
            if f.name in fields:
                vals = [col[i].as_py() for i in range(batch.num_rows)]
                decrypted_vals = self.decrypt_column(vals)
                new_columns.append(pa.array(decrypted_vals, type=pa.string()))
                new_fields.append(pa.field(f.name, pa.string(), nullable=True))
            else:
                new_columns.append(col)
                new_fields.append(f)

        new_schema = pa.schema(new_fields)
        return pa.RecordBatch.from_arrays(new_columns, schema=new_schema)
