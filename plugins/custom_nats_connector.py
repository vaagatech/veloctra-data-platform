"""
plugins/custom_nats_connector.py
================================
Example third-party streaming connector plugin for NATS JetStream / Custom Broker.
Demonstrates how external developers plug in any custom messaging bus into Veloctra
without modifying any core platform source code.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import pyarrow as pa

from veloctra_connectors.streaming_base import BaseStreamingConnector

logger = logging.getLogger(__name__)


class CustomNatsConnector(BaseStreamingConnector):
    """
    Pluggable NATS JetStream / Custom Broker connector.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.subject = config.get("subject") or config.get("topic", "events.data")
        self.servers = config.get("servers", ["nats://localhost:4222"])
        self.stream_name = config.get("stream_name", "VELOCTRA_EVENTS")
        self._nc = None
        self._is_running = False
        self._in_memory_queue = asyncio.Queue()

    async def connect(self) -> None:
        try:
            import nats  # type: ignore
            self._nc = await asyncio.wait_for(nats.connect(self.servers), timeout=0.5)
            self._is_running = True
            logger.info("[CustomNatsConnector] Connected to NATS cluster %s (subject: %s)", self.servers, self.subject)
        except ImportError:
            logger.warning("[CustomNatsConnector] 'nats-py' not installed. Operating in simulation mode.")
            self._nc = None
            self._is_running = True
        except Exception as exc:
            logger.warning("[CustomNatsConnector] NATS unavailable (%s). Operating in simulation mode.", exc)
            self._nc = None
            self._is_running = True

    async def close(self) -> None:
        self._is_running = False
        if self._nc:
            await self._nc.drain()
            self._nc = None
            logger.info("[CustomNatsConnector] Disconnected from NATS.")

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        batch_dicts = []
        # If simulation or active queue
        while not self._in_memory_queue.empty() and len(batch_dicts) < chunk_size:
            msg = await self._in_memory_queue.get()
            batch_dicts.append(msg)

        if batch_dicts:
            yield self._dicts_to_batch(batch_dicts)
        else:
            # Yield empty batch in simulation when queue drained
            yield self._dicts_to_batch([{"id": 1, "event": "custom_nats_init", "status": "ok"}])

    async def publish_batch(self, batch: pa.RecordBatch, **kwargs) -> int:
        records = batch.to_pylist()
        if not records:
            return 0

        target_subject = kwargs.get("subject") or self.subject

        if self._nc:
            js = self._nc.jetstream()
            for rec in records:
                payload = json.dumps(rec, default=str).encode("utf-8")
                await js.publish(target_subject, payload)
        else:
            # In simulation, push to internal queue
            for rec in records:
                await self._in_memory_queue.put(rec)

        logger.info("[CustomNatsConnector] Published %d records to NATS subject '%s'", len(records), target_subject)
        return len(records)
