"""
veloctra_connectors/streaming_base.py
=====================================
Universal Pluggable Streaming Connector Interface & Dynamic Plugin Registry.
Designed for ultra-lightweight deployments (< 40MB RAM) with lazy dependency loading.
Allows plugging in ANY messaging/streaming system (Kafka, RabbitMQ, SQS, Redis,
NATS, Pub/Sub, Azure Event Hubs, MQTT, Solace, or custom enterprise brokers).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Type, Union
import pyarrow as pa

logger = logging.getLogger(__name__)


class StreamingPluginError(Exception):
    """Raised when loading or resolving a streaming connector plugin fails."""
    pass


class BaseStreamingConnector(ABC):
    """
    Standard open contract for all streaming and messaging connectors.
    Inherited by all built-in and third-party streaming plugins.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    async def connect(self) -> None:
        """Initializes connection to broker/service lazily."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Drains and gracefully terminates broker connection."""
        ...

    @abstractmethod
    def stream_read(self, chunk_size: int = 5000) -> AsyncGenerator[pa.RecordBatch, None]:
        """
        Asynchronously streams records from topic/queue yielding PyArrow RecordBatches.
        """
        ...

    @abstractmethod
    async def publish_batch(self, batch: pa.RecordBatch, **kwargs) -> int:
        """
        Publishes a PyArrow RecordBatch to topic/queue/exchange.
        Returns the number of successfully published messages.
        """
        ...

    async def __aenter__(self) -> "BaseStreamingConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    def _dicts_to_batch(self, dicts: List[Dict[str, Any]]) -> pa.RecordBatch:
        """Helper to convert Python dictionaries to PyArrow RecordBatch with type inference."""
        if not dicts:
            return pa.Table.from_pydict({"id": pa.array([], type=pa.int64())}).to_batches()[0]
        keys = list(dicts[0].keys())
        arrays = []
        for key in keys:
            vals = [d.get(key) for d in dicts]
            arrays.append(pa.array(vals))
        table = pa.Table.from_arrays(arrays, names=keys)
        return table.to_batches()[0]


class StreamingConnectorRegistry:
    """
    Dynamic Registry and Loader for pluggable streaming connectors.
    Supports:
    1. Built-in lazy resolution (only loads dependencies when connector is instantiated).
    2. Explicit runtime registration.
    3. External module loading (via plugin_module: "my_pkg.connectors.solace").
    4. Dynamic file loading (via plugin_file: "plugins/custom_nats.py").
    """

    _registry: Dict[str, Union[Type[BaseStreamingConnector], str]] = {
        "kafka": "veloctra_connectors.kafka_connector.KafkaConnector",
        "streaming_kafka": "veloctra_connectors.kafka_connector.KafkaConnector",
        "rabbitmq": "veloctra_connectors.rabbitmq_connector.RabbitmqConnector",
        "amqp": "veloctra_connectors.rabbitmq_connector.RabbitmqConnector",
        "sqs": "veloctra_connectors.aws_sqs_connector.AwsSqsConnector",
        "aws_sqs": "veloctra_connectors.aws_sqs_connector.AwsSqsConnector",
        "redis": "veloctra_connectors.redis_stream_connector.RedisStreamConnector",
        "redis_stream": "veloctra_connectors.redis_stream_connector.RedisStreamConnector",
    }

    @classmethod
    def register(cls, name: str, connector_cls: Type[BaseStreamingConnector]) -> None:
        """Registers a custom streaming connector class under an alias."""
        cls._registry[name.lower()] = connector_cls
        logger.info("[StreamingRegistry] Registered connector plugin '%s' -> %s", name, connector_cls.__name__)

    @classmethod
    def resolve_connector_class(cls, config: Dict[str, Any]) -> Type[BaseStreamingConnector]:
        """Resolves connector class from config via alias, module, or file path."""
        stype = config.get("type", "").lower()
        engine = config.get("engine", "").lower()
        name = engine or stype

        # 1. Check if directly registered class or lazy string import
        if name in cls._registry:
            target = cls._registry[name]
            if isinstance(target, str):
                module_path, class_name = target.rsplit(".", 1)
                mod = importlib.import_module(module_path)
                resolved_cls = getattr(mod, class_name)
                cls._registry[name] = resolved_cls
                return resolved_cls
            return target

        # 2. Dynamic file plugin path
        plugin_file = config.get("plugin_file") or config.get("file_path")
        if plugin_file:
            path = Path(plugin_file)
            if not path.exists():
                raise StreamingPluginError(f"Streaming plugin file '{plugin_file}' does not exist.")
            try:
                mod_name = f"veloctra_stream_plugin_{path.stem}"
                spec = importlib.util.spec_from_file_location(mod_name, path)
                if spec is None or spec.loader is None:
                    raise StreamingPluginError(f"Could not load module spec for '{plugin_file}'")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                class_name = config.get("class_name")
                if class_name and hasattr(mod, class_name):
                    return getattr(mod, class_name)

                # Auto-find subclass of BaseStreamingConnector
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseStreamingConnector) and attr is not BaseStreamingConnector:
                        return attr

                raise StreamingPluginError(f"No BaseStreamingConnector subclass found in '{plugin_file}'")
            except Exception as exc:
                raise StreamingPluginError(f"Failed to load plugin file '{plugin_file}': {exc}") from exc

        # 3. Dynamic Python module path
        plugin_module = config.get("plugin_module") or config.get("module")
        if plugin_module:
            try:
                mod = importlib.import_module(plugin_module)
                class_name = config.get("class_name")
                if class_name and hasattr(mod, class_name):
                    return getattr(mod, class_name)
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseStreamingConnector) and attr is not BaseStreamingConnector:
                        return attr
                raise StreamingPluginError(f"No BaseStreamingConnector subclass found in module '{plugin_module}'")
            except Exception as exc:
                raise StreamingPluginError(f"Failed to import streaming module '{plugin_module}': {exc}") from exc

        raise StreamingPluginError(
            f"Unsupported or unresolvable streaming connector type: '{stype or engine}'. "
            "Specify a supported type or provide 'plugin_file' / 'plugin_module'."
        )


def create_streaming_connector(config: Dict[str, Any]) -> BaseStreamingConnector:
    """Factory function instantiating a streaming connector from pipeline configuration."""
    connector_cls = StreamingConnectorRegistry.resolve_connector_class(config)
    return connector_cls(config)
