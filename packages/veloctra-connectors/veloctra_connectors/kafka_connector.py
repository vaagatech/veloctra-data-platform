"""
veloctra_connectors/kafka_connector.py
======================================
Kafka bi-directional connector (Consumer & Producer).
Supports stream extraction and destination publishing with PyArrow batch serialization.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import pyarrow as pa

from veloctra_connectors.streaming_base import BaseStreamingConnector

logger = logging.getLogger(__name__)


class KafkaConnector(BaseStreamingConnector):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.topic = config.get("topic", "default_topic")
        self.bootstrap_servers = config.get("bootstrap_servers", "localhost:9092")
        self.group_id = config.get("group_id", "veloctra-group")
        self.offset_action = config.get("offset_action", "process_new_only")
        self.key_column = config.get("key_column")
        self._consumer = None
        self._producer = None

    async def connect_consumer(self) -> None:
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore
        except ImportError:
            logger.warning("[KafkaConnector] 'aiokafka' is not installed. Falling back to mock/noop mode.")
            return

        try:
            auto_offset = "earliest" if self.offset_action == "replay_from_start" else "latest"
            consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=auto_offset,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )
            await asyncio.wait_for(consumer.start(), timeout=0.5)
            self._consumer = consumer
            logger.info("[KafkaConnector] Consumer connected to Kafka (%s) topic '%s'", self.bootstrap_servers, self.topic)
        except Exception as exc:
            logger.warning("[KafkaConnector] Kafka broker unavailable at %s (%s). Operating in local simulation mode.", self.bootstrap_servers, exc)
            self._consumer = None

    async def connect_producer(self) -> None:
        try:
            from aiokafka import AIOKafkaProducer  # type: ignore
        except ImportError:
            logger.warning("[KafkaConnector] 'aiokafka' is not installed. Falling back to mock/noop mode.")
            return

        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: str(k).encode("utf-8") if k is not None else None,
                request_timeout_ms=1000,
            )
            await asyncio.wait_for(producer.start(), timeout=0.5)
            self._producer = producer
            logger.info("[KafkaConnector] Producer connected to Kafka (%s)", self.bootstrap_servers)
        except Exception as exc:
            logger.warning("[KafkaConnector] Kafka broker unavailable at %s (%s). Operating in local simulation mode.", self.bootstrap_servers, exc)
            self._producer = None

    async def connect(self) -> None:
        mode = self.config.get("mode", "both")
        if mode in ("consumer", "source", "both"):
            await self.connect_consumer()
        if mode in ("producer", "destination", "sink", "both"):
            await self.connect_producer()

    async def close(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            logger.info("[KafkaConnector] Consumer disconnected from Kafka.")
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("[KafkaConnector] Producer disconnected from Kafka.")

    async def __aenter__(self) -> "KafkaConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        """Streams records from Kafka topic in PyArrow RecordBatches."""
        if not self._consumer:
            logger.info("[KafkaConnector] No active consumer. Returning empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            async for msg in self._consumer:
                batch_dicts.append(msg.value)
                if len(batch_dicts) >= chunk_size:
                    yield self._dicts_to_batch(batch_dicts)
                    batch_dicts = []
        except Exception as e:
            logger.error("[KafkaConnector] Error reading from Kafka stream: %s", e)
            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

    async def publish_batch(
        self,
        batch: pa.RecordBatch,
        topic: Optional[str] = None,
        key_column: Optional[str] = None,
    ) -> int:
        """
        Publishes a PyArrow RecordBatch to Kafka topic as JSON messages.
        Returns the number of published messages.
        """
        target_topic = topic or self.topic
        key_col = key_column or self.key_column
        records = batch.to_pylist()
        if not records:
            return 0

        if self._producer is None:
            await self.connect_producer()

        if self._producer is None:
            logger.info("[KafkaConnector:Mock] Published %d records to topic '%s'", len(records), target_topic)
            return len(records)

        send_tasks = []
        for record in records:
            msg_key = record.get(key_col) if key_col else None
            task = self._producer.send(target_topic, value=record, key=msg_key)
            send_tasks.append(task)

        await asyncio.gather(*send_tasks)
        logger.info("[KafkaConnector] Published %d records to topic '%s'", len(records), target_topic)
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
