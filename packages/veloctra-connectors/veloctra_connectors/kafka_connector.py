"""
veloctra_connectors/kafka_connector.py
======================================
Kafka source connector plugin. Dynamically loaded by the orchestrator.
Requires 'aiokafka' package.
"""

from __future__ import annotations

import logging
import json
from typing import Any, AsyncGenerator, Dict, Optional
import pyarrow as pa

logger = logging.getLogger(__name__)


class KafkaConnector:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.topic = config.get("topic", "default_topic")
        self.bootstrap_servers = config.get("bootstrap_servers", "localhost:9092")
        self.group_id = config.get("group_id", "veloctra-group")
        self.offset_action = config.get("offset_action", "process_new_only")
        self._consumer = None

    async def connect(self) -> None:
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore
        except ImportError:
            logger.error("[KafkaConnector] 'aiokafka' is not installed. Please run: pip install aiokafka")
            return

        auto_offset = "earliest" if self.offset_action == "replay_from_start" else "latest"
        
        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset=auto_offset,
            value_deserializer=lambda m: json.loads(m.decode("utf-8"))
        )
        await self._consumer.start()
        logger.info("[KafkaConnector] Connected to Kafka (%s) topic '%s'", self.bootstrap_servers, self.topic)

    async def close(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            logger.info("[KafkaConnector] Disconnected from Kafka.")

    async def __aenter__(self) -> "KafkaConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._consumer:
            logger.warning("[KafkaConnector] Consumer not initialized. Yielding empty batch.")
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
            logger.error("[KafkaConnector] Error reading from stream: %s", e)
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
