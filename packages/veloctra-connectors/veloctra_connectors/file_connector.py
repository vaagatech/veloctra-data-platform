"""
veloctra_connectors/file_connector.py
=====================================
Universal File Streaming Connector supporting CSV, Compressed ZIP/GZ, and Parquet.
Streams data in zero-copy PyArrow RecordBatches directly into Veloctra Engine.
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Any, AsyncGenerator, Dict, Optional

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

from veloctra_security.secrets_manager import resolve_secret

logger = logging.getLogger(__name__)


class FileConnector:
    """Universal File Source Connector for streaming large CSV, ZIP, Parquet files."""

    def __init__(self, config: Dict[str, Any]):
        self._path = resolve_secret(config.get("path") or config.get("file_path", ""))
        self._format = config.get("format", "csv").lower()
        self._delimiter = config.get("delimiter", ",")
        self._has_header = config.get("has_header", True)
        self._inner_filename = config.get("inner_filename")
        self._zip_file: Optional[zipfile.ZipFile] = None
        self._file_handle = None

    async def connect(self) -> None:
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"Source file not found at '{self._path}'")
        logger.info("[FileConnector] Opened source file at '%s' (format: %s)", self._path, self._format)

    async def close(self) -> None:
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None
        if self._zip_file:
            try:
                self._zip_file.close()
            except Exception:
                pass
            self._zip_file = None
        logger.info("[FileConnector] Closed source file '%s'", self._path)

    async def __aenter__(self) -> "FileConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 10_000) -> AsyncGenerator[pa.RecordBatch, None]:
        """Streams PyArrow RecordBatches directly from the file or zip archive."""
        if self._path.endswith(".zip") or self._format == "zip":
            self._zip_file = zipfile.ZipFile(self._path, "r")
            namelist = self._zip_file.namelist()
            target_name = self._inner_filename or (namelist[0] if namelist else None)
            if not target_name:
                raise ValueError(f"Zip archive '{self._path}' contains no readable files")
            
            logger.info("[FileConnector] Streaming inner file '%s' from zip archive '%s'", target_name, self._path)
            self._file_handle = self._zip_file.open(target_name, "r")
            
            read_options = pa_csv.ReadOptions(block_size=max(chunk_size * 256, 16 * 1024 * 1024))
            parse_options = pa_csv.ParseOptions(delimiter=self._delimiter)
            convert_options = pa_csv.ConvertOptions(strings_can_be_null=True)

            reader = pa_csv.open_csv(
                self._file_handle,
                read_options=read_options,
                parse_options=parse_options,
                convert_options=convert_options,
            )

            for batch in reader:
                norm_batch = batch.rename_columns([name.lower() for name in batch.schema.names])
                if norm_batch.num_rows > chunk_size:
                    offset = 0
                    while offset < norm_batch.num_rows:
                        length = min(chunk_size, norm_batch.num_rows - offset)
                        yield norm_batch.slice(offset, length)
                        offset += length
                else:
                    yield norm_batch

        elif self._path.endswith(".parquet") or self._format == "parquet":
            parquet_file = pq.ParquetFile(self._path)
            for batch in parquet_file.iter_batches(batch_size=chunk_size):
                norm_batch = batch.rename_columns([name.lower() for name in batch.schema.names])
                yield norm_batch

        else:
            # Standard CSV / Text file
            read_options = pa_csv.ReadOptions(block_size=max(chunk_size * 256, 16 * 1024 * 1024))
            parse_options = pa_csv.ParseOptions(delimiter=self._delimiter)
            convert_options = pa_csv.ConvertOptions(strings_can_be_null=True)

            reader = pa_csv.open_csv(
                self._path,
                read_options=read_options,
                parse_options=parse_options,
                convert_options=convert_options,
            )

            for batch in reader:
                norm_batch = batch.rename_columns([name.lower() for name in batch.schema.names])
                if norm_batch.num_rows > chunk_size:
                    offset = 0
                    while offset < norm_batch.num_rows:
                        length = min(chunk_size, norm_batch.num_rows - offset)
                        yield norm_batch.slice(offset, length)
                        offset += length
                else:
                    yield norm_batch
