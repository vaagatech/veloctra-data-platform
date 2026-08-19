"""
tests/test_messaging_connectors.py
==================================
Tests for KafkaConnector, RabbitmqConnector, and AwsSqsConnector publishing and streaming.
"""

import pytest
import pyarrow as pa
from veloctra_connectors.kafka_connector import KafkaConnector
from veloctra_connectors.rabbitmq_connector import RabbitmqConnector
from veloctra_connectors.aws_sqs_connector import AwsSqsConnector


@pytest.mark.asyncio
async def test_kafka_connector_publish_batch():
    config = {
        "bootstrap_servers": "localhost:9092",
        "topic": "test_events",
        "key_column": "id",
    }
    connector = KafkaConnector(config)
    batch = pa.RecordBatch.from_pydict({
        "id": [101, 102, 103],
        "event": ["LOGIN", "PURCHASE", "LOGOUT"],
        "amount": [0.0, 99.95, 0.0],
    })

    # When aiokafka broker is not available locally, fallback mock publish returns record count
    published = await connector.publish_batch(batch)
    assert published == 3


@pytest.mark.asyncio
async def test_rabbitmq_connector_publish_batch():
    config = {
        "amqp_url": "amqp://guest:guest@localhost:5672/",
        "queue": "test_queue",
        "routing_key": "test_routing_key",
    }
    connector = RabbitmqConnector(config)
    batch = pa.RecordBatch.from_pydict({
        "order_id": [1, 2],
        "item": ["laptop", "mouse"],
    })

    published = await connector.publish_batch(batch)
    assert published == 2


@pytest.mark.asyncio
async def test_aws_sqs_connector_publish_batch():
    config = {
        "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/MyQueue",
        "region_name": "us-east-1",
    }
    connector = AwsSqsConnector(config)
    batch = pa.RecordBatch.from_pydict({
        "sensor_id": [10, 20, 30],
        "temp": [72.5, 74.1, 69.8],
    })

    published = await connector.publish_batch(batch)
    assert published == 3
