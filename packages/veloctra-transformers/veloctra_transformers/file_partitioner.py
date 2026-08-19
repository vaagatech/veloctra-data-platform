"""
veloctra_transformers/file_partitioner.py
=========================================
Auto-sized partitioned file sink for Parquet and CSV files.
"""

from __future__ import annotations

import io
import logging
from typing import Dict, List, Optional, Tuple

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from veloctra_connectors.universal_fs import UniversalFileSystem

logger = logging.getLogger(__name__)


class FilePartitioner:
    def __init__(
        self,
        fs: UniversalFileSystem,
        output_dir: str,
        file_format: str = "parquet",
        file_prefix: str = "part",
        max_rows_per_file: int = 100_000,
        max_file_size_mb: float = 100.0,
    ):
        self.fs = fs
        self.output_dir = output_dir.rstrip("/")
        self.file_format = file_format.lower()
        self.file_prefix = file_prefix
        self.max_rows_per_file = max_rows_per_file
        self.max_bytes_per_file = int(max_file_size_mb * 1024 * 1024)

        self._part_index = 1
        self._current_buffer: List[pa.RecordBatch] = []
        self._current_row_count = 0
        self._current_byte_estimate = 0

    def write_batch(self, batch: pa.RecordBatch) -> List[str]:
        if batch.num_rows == 0:
            return []

        written_files: List[str] = []
        self._current_buffer.append(batch)
        self._current_row_count += batch.num_rows
        self._current_byte_estimate += batch.nbytes

        if (
            self._current_row_count >= self.max_rows_per_file
            or self._current_byte_estimate >= self.max_bytes_per_file
        ):
            file_path = self.flush()
            if file_path:
                written_files.append(file_path)

        return written_files

    def flush(self) -> Optional[str]:
        if not self._current_buffer:
            return None

        combined_table = pa.Table.from_batches(self._current_buffer)
        filename = f"{self.file_prefix}_{self._part_index:05d}.{self.file_format}"
        target_path = f"{self.output_dir}/{filename}"

        out_stream = io.BytesIO()
        if self.file_format == "parquet":
            pq.write_table(combined_table, out_stream, compression="snappy")
        elif self.file_format == "csv":
            df = pl.from_arrow(combined_table)
            out_stream.write(df.write_csv().encode("utf-8"))
        else:
            raise ValueError(f"Unsupported partition file format: '{self.file_format}'")

        data_bytes = out_stream.getvalue()
        saved_path = self.fs.write_atomic(target_path, data_bytes)

        self._part_index += 1
        self._current_buffer = []
        self._current_row_count = 0
        self._current_byte_estimate = 0

        logger.info("[Partitioner] Flushed %d rows -> %s (%d bytes)", combined_table.num_rows, saved_path, len(data_bytes))
        return saved_path
