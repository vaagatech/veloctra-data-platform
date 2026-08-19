"""
veloctra_connectors/aws_sqs_connector.py
========================================
AWS SQS source connector plugin. Dynamically loaded by the orchestrator.
Requires 'aiobotocore' package.
"""

from __future__ import annotations

import logging
import json
from typing import Any, AsyncGenerator, Dict, Optional
import pyarrow as pa

logger = logging.getLogger(__name__)


class AwsSqsConnector:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.queue_url = config.get("queue_url")
        self.region_name = config.get("region_name", "us-east-1")
        self.offset_action = config.get("offset_action", "process_new_only")
        self._session = None
        self._client = None
        self._is_running = False

    async def connect(self) -> None:
        try:
            from aiobotocore.session import get_session  # type: ignore
        except ImportError:
            logger.error("[AwsSqsConnector] 'aiobotocore' is not installed. Please run: pip install aiobotocore")
            return
            
        if not self.queue_url:
            logger.error("[AwsSqsConnector] queue_url is required in the configuration.")
            return

        self._session = get_session()
        self._client = await self._session.create_client('sqs', region_name=self.region_name).__aenter__()
        
        # SQS doesn't replay messages natively once deleted. If 'replay_from_start' is requested,
        # it would require a custom setup (like DLQ replay). Just log for now.
        if self.offset_action == "replay_from_start":
            logger.warning("[AwsSqsConnector] SQS does not support native replay_from_start unless a custom DLQ mechanism is used.")

        self._is_running = True
        logger.info("[AwsSqsConnector] Connected to SQS queue '%s'", self.queue_url)

    async def close(self) -> None:
        self._is_running = False
        if self._client:
            await self._client.__aexit__(None, None, None)
            logger.info("[AwsSqsConnector] Disconnected from SQS.")

    async def __aenter__(self) -> "AwsSqsConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._client:
            logger.warning("[AwsSqsConnector] SQS client not initialized. Yielding empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            while self._is_running:
                response = await self._client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=5
                )

                messages = response.get('Messages', [])
                if not messages:
                    # Optional: Break if queue is empty and we are not doing continuous stream
                    continue

                entries_to_delete = []
                for msg in messages:
                    try:
                        payload = json.loads(msg['Body'])
                        batch_dicts.append(payload)
                        entries_to_delete.append({
                            'Id': msg['MessageId'],
                            'ReceiptHandle': msg['ReceiptHandle']
                        })
                    except Exception as parse_exc:
                        logger.warning("[AwsSqsConnector] Failed to parse message body: %s", parse_exc)

                # Delete processed messages
                if entries_to_delete:
                    await self._client.delete_message_batch(
                        QueueUrl=self.queue_url,
                        Entries=entries_to_delete
                    )

                if len(batch_dicts) >= chunk_size:
                    yield self._dicts_to_batch(batch_dicts)
                    batch_dicts = []
                    
        except Exception as e:
            logger.error("[AwsSqsConnector] Error reading from stream: %s", e)
        finally:
            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

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
