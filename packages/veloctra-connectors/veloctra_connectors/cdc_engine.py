"""
veloctra_connectors/cdc_engine.py
=================================
Universal Change Data Capture (CDC) engine supporting:
1. Snapshot Row-Checksum Hash-Diff CDC (for tables with NO timestamp/watermark columns).
2. MongoDB Change Stream Oplog CDC (with resume tokens).
3. CDC Change Batch generation with unified (_cdc_op: INSERT | UPDATE | DELETE) metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

import pyarrow as pa

logger = logging.getLogger(__name__)


def compute_row_hash(row: Dict[str, Any], key_cols: Optional[List[str]] = None) -> str:
    """Computes a deterministic SHA-256 hash of non-key row contents."""
    row_copy = {k: v for k, v in row.items() if not key_cols or k not in key_cols}
    serialized = json.dumps(row_copy, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ChecksumDiffCDC:
    """
    Computes Change Data Capture deltas (INSERT, UPDATE, DELETE) for tables
    that have NO timestamps, NO updated_at columns, and NO replication stream access.
    Compares the incoming table snapshot against the previous state hash map.
    """

    def __init__(self, key_columns: List[str]):
        self.key_columns = key_columns
        self._previous_state: Dict[str, str] = {}  # key_str -> row_hash
        self._key_values_cache: Dict[str, Dict[str, Any]] = {}

    def load_state(self, state_dict: Dict[str, str]) -> None:
        self._previous_state = dict(state_dict)

    def get_state(self) -> Dict[str, str]:
        return dict(self._previous_state)

    def process_snapshot(self, batch: pa.RecordBatch) -> Tuple[pa.RecordBatch, Dict[str, str]]:
        """
        Diffs the incoming batch rows against the previous state.
        Returns:
            Tuple of (cdc_record_batch, new_state_dict)
        """
        rows = batch.to_pylist()
        current_keys: Set[str] = set()
        new_state: Dict[str, str] = dict(self._previous_state)

        cdc_records: List[Dict[str, Any]] = []
        now = time.time()

        for row in rows:
            # Build compound key string and preserve typed key dictionary
            key_val = ":".join(str(row.get(k, "")) for k in self.key_columns)
            key_dict = {k: row.get(k) for k in self.key_columns}
            self._key_values_cache[key_val] = key_dict
            current_keys.add(key_val)
            row_hash = compute_row_hash(row, self.key_columns)

            if key_val not in self._previous_state:
                # 1. New Record -> INSERT
                cdc_row = dict(row)
                cdc_row["_cdc_op"] = "INSERT"
                cdc_row["_cdc_ts"] = now
                cdc_row["_cdc_key"] = key_val
                cdc_records.append(cdc_row)
                new_state[key_val] = row_hash
            elif self._previous_state[key_val] != row_hash:
                # 2. Changed Record -> UPDATE
                cdc_row = dict(row)
                cdc_row["_cdc_op"] = "UPDATE"
                cdc_row["_cdc_ts"] = now
                cdc_row["_cdc_key"] = key_val
                cdc_records.append(cdc_row)
                new_state[key_val] = row_hash

        # 3. Detect Deletions (keys in previous state that no longer exist)
        for old_key in list(self._previous_state.keys()):
            if old_key not in current_keys:
                del_row = {k: None for k in batch.schema.names}
                old_key_vals = self._key_values_cache.get(old_key, {})
                for k, v in old_key_vals.items():
                    del_row[k] = v
                del_row["_cdc_op"] = "DELETE"
                del_row["_cdc_ts"] = now
                del_row["_cdc_key"] = old_key
                cdc_records.append(del_row)
                new_state.pop(old_key, None)
                self._key_values_cache.pop(old_key, None)

        self._previous_state = new_state

        if not cdc_records:
            return batch.slice(0, 0), new_state

        cdc_batch = pa.RecordBatch.from_pylist(cdc_records)
        return cdc_batch, new_state


class MongoChangeStreamCDC:
    """
    Subscribes to MongoDB Change Streams (Oplog) with resume tokens for real-time CDC.
    """

    def __init__(self, db_client: Any, db_name: str, collection_name: str):
        self.db_client = db_client
        self.db_name = db_name
        self.collection_name = collection_name
        self.resume_token: Optional[Dict[str, Any]] = None

    async def stream_changes(
        self,
        resume_token: Optional[Dict[str, Any]] = None,
        max_events: int = 5000,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        db = self.db_client[self.db_name]
        coll = db[self.collection_name]

        watch_options = {}
        if resume_token:
            watch_options["resume_after"] = resume_token

        async with coll.watch(**watch_options) as stream:
            buffer: List[Dict[str, Any]] = []
            async for change in stream:
                self.resume_token = stream.resume_token
                op_type = change.get("operationType", "insert").upper()

                doc = change.get("fullDocument") or {}
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

                doc["_cdc_op"] = op_type
                doc["_cdc_ts"] = time.time()
                doc["_cdc_key"] = str(change.get("documentKey", {}).get("_id", ""))

                buffer.append(doc)
                if len(buffer) >= max_events:
                    yield pa.RecordBatch.from_pylist(buffer)
                    buffer = []

            if buffer:
                yield pa.RecordBatch.from_pylist(buffer)
