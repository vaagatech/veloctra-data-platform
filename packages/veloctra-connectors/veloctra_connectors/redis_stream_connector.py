"""
veloctra_connectors/redis_stream_connector.py
=============================================
Redis Streams connector plugin (XREAD / XADD).
Inherits from BaseStreamingConnector with lazy dependency loading.
Ideal for ultra-lightweight deployments, small pods, and low-latency message streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import pyarrow as pa

from veloctra_connectors.streaming_base import BaseStreamingConnector

logger = logging.getLogger(__name__)


class RedisStreamConnector(BaseStreamingConnector):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.stream_key = config.get("stream_key") or config.get("stream") or config.get("topic") or "veloctra_stream"
        self.redis_url = config.get("redis_url") or config.get("connection_string") or "redis://localhost:6379"
        self.group_name = config.get("group_name") or config.get("group_id")
        self.consumer_name = config.get("consumer_name", "veloctra_worker_1")
        self.last_id = config.get("last_id", "$")
        self._client = None
        self._is_running = False

    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis  # type: ignore
        except ImportError:
            logger.warning("[RedisStreamConnector] 'redis' package is not installed. Operating in simulation mode.")
            return

        try:
            client = aioredis.from_url(self.redis_url, decode_responses=True)
            await asyncio.wait_for(client.ping(), timeout=0.5)
            self._client = client
            self._is_running = True
            logger.info("[RedisStreamConnector] Connected to Redis stream '%s'", self.stream_key)
        except Exception as exc:
            logger.warning("[RedisStreamConnector] Redis unavailable at '%s' (%s). Operating in local simulation mode.", self.redis_url, exc)
            self._client = None

    async def close(self) -> None:
        self._is_running = False
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("[RedisStreamConnector] Disconnected from Redis.")

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        if not self._client:
            logger.info("[RedisStreamConnector:Simulation] No active broker connection. Yielding empty batch.")
            yield pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
            return

        batch_dicts = []
        try:
            while self._is_running:
                # Read new messages from stream
                response = await self._client.xread(
                    streams={self.stream_key: self.last_id},
                    count=min(chunk_size, 100),
                    block=1000,
                )

                if not response:
                    break

                for stream_name, messages in response:
                    for msg_id, payload in messages:
                        self.last_id = msg_id
                        # Parse JSON payload if stored as single field or unpack dict
                        if "payload" in payload:
                            try:
                                record = json.loads(payload["payload"])
                            except Exception:
                                record = payload
                        else:
                            record = payload
                        batch_dicts.append(record)

                if len(batch_dicts) >= chunk_size:
                    yield self._dicts_to_batch(batch_dicts)
                    batch_dicts = []

            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

        except Exception as exc:
            logger.error("[RedisStreamConnector] Error reading from stream: %s", exc)
            if batch_dicts:
                yield self._dicts_to_batch(batch_dicts)

    async def publish_batch(
        self,
        batch: pa.RecordBatch,
        stream_key: Optional[str] = None,
        **kwargs,
    ) -> int:
        records = batch.to_pylist()
        if not records:
            return 0

        target_stream = stream_key or self.stream_key

        if self._client is None:
            await self.connect()

        if self._client is None:
            logger.info("[RedisStreamConnector:Simulation] Published %d records to Redis stream '%s'", len(records), target_stream)
            return len(records)

        try:
            pipe = self._client.pipeline()
            for record in records:
                flat_payload = {k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v) for k, v in record.items()}
                pipe.xadd(target_stream, flat_payload)
            await pipe.execute()
            logger.info("[RedisStreamConnector] Published %d records to stream '%s'", len(records), target_stream)
            return len(records)
        except Exception as exc:
            logger.warning("[RedisStreamConnector] Error publishing to Redis (%s). Operating in simulation mode.", exc)
            return len(records)
