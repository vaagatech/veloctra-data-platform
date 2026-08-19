"""
tests/test_pluggable_streaming.py
=================================
Tests for the Pluggable Streaming Connector Interface, Dynamic Registry,
and external plugin loading for lightweight pod deployments.
"""

import pytest
import pyarrow as pa
import asyncio
from typing import AsyncGenerator, Dict, Any

from veloctra_connectors.streaming_base import (
    BaseStreamingConnector,
    StreamingConnectorRegistry,
    create_streaming_connector,
    StreamingPluginError,
)
from veloctra_connectors.redis_stream_connector import RedisStreamConnector
from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_security.security import TokenPayload


class MockInMemoryConnector(BaseStreamingConnector):
    """Test custom connector registered dynamically at runtime."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.published_records = []
        self.is_connected = False

    async def connect(self) -> None:
        self.is_connected = True

    async def close(self) -> None:
        self.is_connected = False

    async def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        data = [
            {"sensor_id": "SN-101", "temperature": 23.5, "status": "active"},
            {"sensor_id": "SN-102", "temperature": 24.1, "status": "active"},
            {"sensor_id": "SN-103", "temperature": 22.8, "status": "active"},
        ]
        yield self._dicts_to_batch(data)

    async def publish_batch(self, batch: pa.RecordBatch, **kwargs) -> int:
        records = batch.to_pylist()
        self.published_records.extend(records)
        return len(records)


def test_registry_built_in_resolution():
    """Verify built-in aliases resolve lazily without error."""
    kafka_conn = create_streaming_connector({"type": "kafka", "bootstrap_servers": "localhost:9092"})
    assert isinstance(kafka_conn, BaseStreamingConnector)

    rabbit_conn = create_streaming_connector({"type": "rabbitmq", "queue": "test_q"})
    assert isinstance(rabbit_conn, BaseStreamingConnector)

    sqs_conn = create_streaming_connector({"type": "sqs", "queue_url": "https://sqs.dummy/queue"})
    assert isinstance(sqs_conn, BaseStreamingConnector)

    redis_conn = create_streaming_connector({"type": "redis_stream", "stream_key": "my_stream"})
    assert isinstance(redis_conn, RedisStreamConnector)


def test_runtime_custom_plugin_registration():
    """Verify third-party developers can register custom connectors in memory."""
    StreamingConnectorRegistry.register("mock_sensor_bus", MockInMemoryConnector)
    conn = create_streaming_connector({"type": "mock_sensor_bus"})
    assert isinstance(conn, MockInMemoryConnector)


@pytest.mark.asyncio
async def test_dynamic_file_plugin_loading():
    """Verify loading custom connector dynamically from external plugin file."""
    config = {
        "type": "streaming",
        "plugin_file": "plugins/custom_nats_connector.py",
        "class_name": "CustomNatsConnector",
        "subject": "orders.v1",
    }
    conn = create_streaming_connector(config)
    assert isinstance(conn, BaseStreamingConnector)
    assert conn.__class__.__name__ == "CustomNatsConnector"

    async with conn:
        batch = conn._dicts_to_batch([{"order_id": 99, "amount": 150.0}])
        sent = await conn.publish_batch(batch)
        assert sent == 1

        read_batches = []
        async for b in conn.stream_read(chunk_size=10):
            read_batches.append(b)
        assert len(read_batches) >= 1
        assert read_batches[0].num_rows >= 1


def test_plugin_loading_errors():
    """Verify informative errors for nonexistent files or missing classes."""
    with pytest.raises(StreamingPluginError, match="does not exist"):
        create_streaming_connector({
            "type": "streaming",
            "plugin_file": "plugins/non_existent_connector.py",
        })

    with pytest.raises(StreamingPluginError, match="Unsupported or unresolvable"):
        create_streaming_connector({"type": "unknown_future_broker_xyz"})


@pytest.mark.asyncio
async def test_redis_stream_connector_simulation():
    """Verify RedisStreamConnector operations in standalone simulation mode."""
    conn = RedisStreamConnector({"stream_key": "orders_stream", "redis_url": "redis://localhost:6379"})
    batch = conn._dicts_to_batch([{"item_id": 1, "price": 49.99}, {"item_id": 2, "price": 89.50}])

    sent = await conn.publish_batch(batch)
    assert sent == 2


@pytest.mark.asyncio
async def test_orchestrator_custom_streaming_plugin_pipeline():
    """Verify end-to-end pipeline execution with dynamic plugin file streaming source and sink."""
    import tempfile
    import os
    from veloctra_state.fsm import PipelineFSM
    from veloctra_state.state_store import StateStore

    fd, state_path = tempfile.mkstemp(suffix="_stream_state.db")
    os.close(fd)

    try:
        pipeline_cfg = {
            "pipeline": {
                "name": "nats_plugin_test",
                "description": "Dynamic plugin pipeline test",
            },
            "sources": [
                {
                    "name": "custom_nats_source",
                    "type": "streaming",
                    "plugin_file": "plugins/custom_nats_connector.py",
                    "subject": "events.telemetry",
                }
            ],
            "destinations": [
                {
                    "name": "redis_sink",
                    "type": "redis_stream",
                    "stream_key": "out_telemetry",
                }
            ],
            "settings": {
                "chunk_size": 100,
            }
        }

        store = StateStore(adapter_type="sqlite", db_path=state_path)
        await store.connect()
        fsm = PipelineFSM()

        job_id = "job_stream_plugin_001"
        tenant_id = "tenant_stream"
        await fsm.create_job(job_id, tenant_id)

        orchestrator = PipelineOrchestrator(
            job_id=job_id,
            tenant_id=tenant_id,
            config=pipeline_cfg,
            fsm=fsm,
            store=store,
        )

        rows = await orchestrator.run()
        assert rows >= 1
    finally:
        if os.path.exists(state_path):
            try:
                os.remove(state_path)
            except OSError:
                pass
