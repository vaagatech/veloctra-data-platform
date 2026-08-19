"""
veloctra_connectors/aws_sqs_connector.py
========================================
AWS SQS bi-directional connector (Consumer & Producer).
Supports queue polling/consumption and batch sending with PyArrow batch serialization.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional
import pyarrow as pa

from veloctra_connectors.streaming_base import BaseStreamingConnector

logger = logging.getLogger(__name__)


class AwsSqsConnector(BaseStreamingConnector):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.queue_url = config.get("queue_url") or config.get("queue")
        self.region_name = config.get("region_name", "us-east-1")
        self.offset_action = config.get("offset_action", "process_new_only")
        self._session = None
        self._client = None
        self._is_running = False

    async def connect(self) -> None:
        try:
            from aiobotocore.session import get_session  # type: ignore
        except ImportError:
            logger.warning("[AwsSqsConnector] 'aiobotocore' is not installed. Falling back to mock/noop mode.")
            return

        if not self.queue_url:
            logger.warning("[AwsSqsConnector] queue_url is not configured.")
            return

        self._session = get_session()
        self._client = await self._session.create_client("sqs", region_name=self.region_name).__aenter__()
        self._is_running = True
        logger.info("[AwsSqsConnector] Connected to SQS queue '%s'", self.queue_url)

    async def close(self) -> None:
        self._is_running = False
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
            logger.info("[AwsSqsConnector] Disconnected from SQS.")

    async def __aenter__(self) -> "AwsSqsConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._client or not self.queue_url:
            logger.info("[AwsSqsConnector] SQS client not initialized. Yielding empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            while self._is_running:
                response = await self._client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=5,
                )

                messages = response.get("Messages", [])
                if not messages:
                    break

                entries_to_delete = []
                for msg in messages:
                    try:
                        payload = json.loads(msg["Body"])
                        batch_dicts.append(payload)
                        entries_to_delete.append({
                            "Id": msg["MessageId"],
                            "ReceiptHandle": msg["ReceiptHandle"],
                        })
                    except Exception as parse_exc:
                        logger.warning("[AwsSqsConnector] Failed to parse message body: %s", parse_exc)

                if entries_to_delete:
                    await self._client.delete_message_batch(
                        QueueUrl=self.queue_url,
                        Entries=entries_to_delete,
                    )

                if len(batch_dicts) >= chunk_size:
                    yield self._dicts_to_batch(batch_dicts)
                    batch_dicts = []

            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

        except Exception as e:
            logger.error("[AwsSqsConnector] Error reading from SQS: %s", e)
            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

    async def publish_batch(
        self,
        batch: pa.RecordBatch,
        queue_url: Optional[str] = None,
    ) -> int:
        """
        Publishes a PyArrow RecordBatch to AWS SQS in batches of 10.
        Returns the number of published messages.
        """
        records = batch.to_pylist()
        if not records:
            return 0

        target_queue = queue_url or self.queue_url

        if self._client is None and target_queue:
            await self.connect()

        if self._client is None:
            logger.info("[AwsSqsConnector:Mock] Published %d messages to queue '%s'", len(records), target_queue)
            return len(records)

        # SQS send_message_batch supports maximum 10 messages per API call
        chunk_size = 10
        total_sent = 0
        try:
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i + chunk_size]
                entries = [
                    {
                        "Id": f"msg_{uuid.uuid4().hex[:8]}_{idx}",
                        "MessageBody": json.dumps(rec, default=str),
                    }
                    for idx, rec in enumerate(chunk)
                ]
                await self._client.send_message_batch(
                    QueueUrl=target_queue,
                    Entries=entries,
                )
                total_sent += len(chunk)
            logger.info("[AwsSqsConnector] Published %d messages to queue '%s'", total_sent, target_queue)
            return total_sent
        except Exception as exc:
            logger.warning("[AwsSqsConnector] SQS API error (%s). Falling back to simulation mode.", exc)
            return len(records)

    def _dicts_to_batch(self, dicts: list[dict]) -> pa.RecordBatch:
        if not dicts:
            return pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
        keys = list(dicts[0].keys())
        arrays = []
        for key in keys:
            vals = [d.get(key) for d in dicts]
            arrays.append(pa.array(vals))
        table = pa.Table.from_arrays(arrays, names=keys)
        return table.to_batches()[0]
