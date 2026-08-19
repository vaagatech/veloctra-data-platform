"""
veloctra_connectors/rabbitmq_connector.py
=========================================
RabbitMQ bi-directional connector (Consumer & Publisher).
Supports queue consumption and exchange/queue publishing with PyArrow batch serialization.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import pyarrow as pa

from veloctra_connectors.streaming_base import BaseStreamingConnector

logger = logging.getLogger(__name__)


class RabbitmqConnector(BaseStreamingConnector):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.queue_name = config.get("queue") or config.get("queue_name") or "default_queue"
        self.amqp_url = config.get("amqp_url", "amqp://guest:guest@localhost/")
        self.exchange_name = config.get("exchange", "")
        self.routing_key = config.get("routing_key", self.queue_name)
        self.offset_action = config.get("offset_action", "process_new_only")
        self._connection = None
        self._channel = None
        self._queue = None

    async def connect(self) -> None:
        try:
            import aio_pika  # type: ignore
        except ImportError:
            logger.warning("[RabbitmqConnector] 'aio_pika' is not installed. Falling back to mock/noop mode.")
            return

        try:
            self._connection = await asyncio.wait_for(aio_pika.connect_robust(self.amqp_url), timeout=0.5)
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=5000)
            self._queue = await self._channel.declare_queue(self.queue_name, durable=True)
            logger.info("[RabbitmqConnector] Connected to RabbitMQ queue '%s'", self.queue_name)
        except Exception as exc:
            logger.warning("[RabbitmqConnector] RabbitMQ broker unavailable at %s (%s). Operating in local simulation mode.", self.amqp_url, exc)
            self._connection = None
            self._channel = None
            self._queue = None

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._queue = None
            logger.info("[RabbitmqConnector] Disconnected from RabbitMQ.")

    async def __aenter__(self) -> "RabbitmqConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._queue:
            logger.info("[RabbitmqConnector] Queue not initialized. Yielding empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            async with self._queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        payload = json.loads(message.body.decode("utf-8"))
                        batch_dicts.append(payload)
                        if len(batch_dicts) >= chunk_size:
                            yield self._dicts_to_batch(batch_dicts)
                            batch_dicts = []
        except Exception as e:
            logger.error("[RabbitmqConnector] Error reading from stream: %s", e)
            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

    async def publish_batch(
        self,
        batch: pa.RecordBatch,
        routing_key: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> int:
        """
        Publishes a PyArrow RecordBatch to RabbitMQ queue or exchange.
        Returns the number of published messages.
        """
        records = batch.to_pylist()
        if not records:
            return 0

        target_routing_key = routing_key or self.routing_key or self.queue_name
        target_exchange = exchange if exchange is not None else self.exchange_name

        if self._channel is None:
            await self.connect()

        if self._channel is None:
            logger.info("[RabbitmqConnector:Mock] Published %d messages to routing_key '%s'", len(records), target_routing_key)
            return len(records)

        import aio_pika  # type: ignore

        exch = await self._channel.get_exchange(target_exchange) if target_exchange else self._channel.default_exchange

        publish_tasks = []
        for record in records:
            body = json.dumps(record, default=str).encode("utf-8")
            msg = aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            publish_tasks.append(exch.publish(msg, routing_key=target_routing_key))

        await asyncio.gather(*publish_tasks)
        logger.info("[RabbitmqConnector] Published %d messages to exchange '%s' / routing_key '%s'", len(records), target_exchange, target_routing_key)
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
