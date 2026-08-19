"""
veloctra_connectors/universal_fs.py
===================================
Universal file system abstraction using fsspec.
"""

from __future__ import annotations

import logging, os, tempfile, uuid
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

import fsspec

from veloctra_security.secrets_manager import resolve_secret

logger = logging.getLogger(__name__)


class UniversalFileSystem:
    def __init__(self, protocol: str = "file", storage_options: Optional[Dict[str, Any]] = None):
        self.protocol = protocol.lower()
        opts = storage_options or {}
        resolved_opts = {}
        for k, v in opts.items():
            resolved_opts[k] = resolve_secret(v) if isinstance(v, str) else v

        if self.protocol == "s3":
            if "key" not in resolved_opts and "AWS_ACCESS_KEY_ID" in os.environ:
                resolved_opts["key"] = os.environ["AWS_ACCESS_KEY_ID"]
            if "secret" not in resolved_opts and "AWS_SECRET_ACCESS_KEY" in os.environ:
                resolved_opts["secret"] = os.environ["AWS_SECRET_ACCESS_KEY"]

        self._fs: fsspec.AbstractFileSystem = fsspec.filesystem(self.protocol, **resolved_opts)
        logger.info("[UniversalFS] Initialised '%s' filesystem", self.protocol)

    def write_atomic(self, target_path: str, data: bytes) -> str:
        clean_path = self._normalise_path(target_path)
        dir_path = str(Path(clean_path).parent)

        if not self._fs.exists(dir_path):
            self._fs.makedirs(dir_path, exist_ok=True)

        tmp_filename = f".tmp_{uuid.uuid4().hex[:8]}_{Path(clean_path).name}"
        tmp_path = f"{dir_path}/{tmp_filename}" if dir_path != "." else tmp_filename

        try:
            with self._fs.open(tmp_path, "wb") as f:
                f.write(data)

            if self._fs.exists(clean_path):
                self._fs.rm(clean_path)

            self._fs.rename(tmp_path, clean_path)
            logger.info("[UniversalFS] Atomic write complete -> %s", clean_path)
            return clean_path

        except Exception as exc:
            if self._fs.exists(tmp_path):
                try:
                    self._fs.rm(tmp_path)
                except Exception:
                    pass
            raise RuntimeError(f"Failed atomic write to '{clean_path}': {exc}") from exc

    def open_write(self, target_path: str, mode: str = "wb") -> BinaryIO:
        clean_path = self._normalise_path(target_path)
        dir_path = str(Path(clean_path).parent)
        if not self._fs.exists(dir_path):
            self._fs.makedirs(dir_path, exist_ok=True)
        return self._fs.open(clean_path, mode)

    def read_bytes(self, source_path: str) -> bytes:
        clean_path = self._normalise_path(source_path)
        with self._fs.open(clean_path, "rb") as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return self._fs.exists(self._normalise_path(path))

    def list_files(self, path: str, pattern: str = "*") -> List[str]:
        clean_path = self._normalise_path(path)
        if not self._fs.exists(clean_path):
            return []
        items = self._fs.glob(f"{clean_path}/{pattern}")
        return [self._normalise_path(i) for i in items if self._fs.isfile(i)]

    def delete(self, path: str) -> bool:
        clean_path = self._normalise_path(path)
        if self._fs.exists(clean_path):
            self._fs.rm(clean_path, recursive=True)
            return True
        return False

    def _normalise_path(self, path: str) -> str:
        if self.protocol in ("s3", "gcs", "abfs") and "://" in path:
            return path.split("://", 1)[1]
        return path
