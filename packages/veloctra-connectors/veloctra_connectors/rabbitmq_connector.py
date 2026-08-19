"""
veloctra_connectors/rabbitmq_connector.py
=========================================
RabbitMQ source connector plugin. Dynamically loaded by the orchestrator.
Requires 'aio_pika' package.
"""

from __future__ import annotations

import logging
import json
from typing import Any, AsyncGenerator, Dict, Optional
import pyarrow as pa

logger = logging.getLogger(__name__)


class RabbitmqConnector:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.queue_name = config.get("queue", "default_queue")
        self.amqp_url = config.get("amqp_url", "amqp://guest:guest@localhost/")
        self.offset_action = config.get("offset_action", "process_new_only")
        self._connection = None
        self._channel = None
        self._queue = None

    async def connect(self) -> None:
        try:
            import aio_pika  # type: ignore
        except ImportError:
            logger.error("[RabbitmqConnector] 'aio_pika' is not installed. Please run: pip install aio-pika")
            return

        self._connection = await aio_pika.connect_robust(self.amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=5000)
        self._queue = await self._channel.declare_queue(self.queue_name, durable=True)
        
        # If offset_action is 'process_new_only', we could potentially purge the queue or acknowledge old messages
        if self.offset_action == "process_new_only":
            # Just log that we're ignoring old messages. AMQP doesn't easily "replay" unless it's a stream queue.
            logger.info("[RabbitmqConnector] RabbitMQ doesn't natively replay. Consuming current queue state.")
            
        logger.info("[RabbitmqConnector] Connected to RabbitMQ queue '%s'", self.queue_name)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            logger.info("[RabbitmqConnector] Disconnected from RabbitMQ.")

    async def __aenter__(self) -> "RabbitmqConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._queue:
            logger.warning("[RabbitmqConnector] Queue not initialized. Yielding empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            async with self._queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        payload = json.loads(message.body.decode('utf-8'))
                        batch_dicts.append(payload)
                        if len(batch_dicts) >= chunk_size:
                            yield self._dicts_to_batch(batch_dicts)
                            batch_dicts = []
        except Exception as e:
            logger.error("[RabbitmqConnector] Error reading from stream: %s", e)
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
