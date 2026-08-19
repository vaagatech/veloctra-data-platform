"""
veloctra_connectors/nosql_connector.py
======================================
Universal NoSQL interface supporting MongoDB, Apache Cassandra, and AWS DynamoDB.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

import pyarrow as pa

from veloctra_security.secrets_manager import resolve_secret
from veloctra_resilience.retry import async_retry

logger = logging.getLogger(__name__)


class BaseNoSQLConnector(ABC):
    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    @abstractmethod
    def stream_read(
        self,
        collection: str,
        query: Optional[Dict] = None,
        projection: Optional[List[str]] = None,
        chunk_size: int = 10_000,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        ...


    @abstractmethod
    async def bulk_write(
        self,
        collection: str,
        records: List[Dict[str, Any]],
        upsert_key: Optional[str] = None,
    ) -> None:
        ...

    async def __aenter__(self) -> "BaseNoSQLConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


class MongoConnector(BaseNoSQLConnector):
    def __init__(self, uri: str, db_name: str):
        self._uri = resolve_secret(uri)
        self._db_name = db_name
        self._client = None
        self._db = None

    async def connect(self) -> None:
        import motor.motor_asyncio
        self._client = motor.motor_asyncio.AsyncIOMotorClient(self._uri)
        self._db = self._client[self._db_name]
        logger.info("[Mongo] Connected to '%s' db '%s'", self._uri, self._db_name)

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            logger.info("[Mongo] Client closed")

    async def stream_read(
        self,
        collection: str,
        query: Optional[Dict] = None,
        projection: Optional[List[str]] = None,
        chunk_size: int = 10_000,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        if self._db is None:
            raise RuntimeError("Mongo database connection is not initialized. Call connect() first.")
        coll = self._db[collection]
        proj_dict = {f: 1 for f in projection} if projection else None
        cursor = coll.find(query or {}, proj_dict)

        buffer: List[Dict] = []
        async for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            buffer.append(doc)
            if len(buffer) >= chunk_size:
                yield pa.RecordBatch.from_pylist(buffer)
                buffer = []

        if buffer:
            yield pa.RecordBatch.from_pylist(buffer)

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_write(
        self,
        collection: str,
        records: List[Dict[str, Any]],
        upsert_key: Optional[str] = None,
    ) -> None:
        if not records:
            return
        if self._db is None:
            raise RuntimeError("Mongo database connection is not initialized. Call connect() first.")
        import decimal
        from bson.decimal128 import Decimal128
        from pymongo import ReplaceOne, InsertOne
        coll = self._db[collection]

        def _clean(val: Any) -> Any:
            if isinstance(val, decimal.Decimal):
                return Decimal128(val)
            if isinstance(val, dict):
                return {k: _clean(v) for k, v in val.items()}
            if isinstance(val, list):
                return [_clean(i) for i in val]
            return val

        cleaned_records = [_clean(r) for r in records]

        if upsert_key:
            requests = [
                ReplaceOne({upsert_key: r[upsert_key]}, r, upsert=True)
                for r in cleaned_records if upsert_key in r
            ]
        else:
            requests = [InsertOne(r) for r in cleaned_records]

        result = await coll.bulk_write(requests, ordered=False)
        logger.info("[Mongo] Bulk write to '%s': %d written", collection, len(records))


class CassandraConnector(BaseNoSQLConnector):
    def __init__(self, hosts: List[str], keyspace: str, port: int = 9042):
        self._hosts = hosts
        self._keyspace = keyspace
        self._port = port
        self._cluster = None
        self._session = None

    async def connect(self) -> None:
        from cassandra.cluster import Cluster
        self._cluster = Cluster(contact_points=self._hosts, port=self._port)
        self._session = self._cluster.connect(self._keyspace)
        logger.info("[Cassandra] Connected to keyspace '%s'", self._keyspace)

    async def close(self) -> None:
        if self._cluster:
            self._cluster.shutdown()
            self._cluster = None
            logger.info("[Cassandra] Cluster shutdown")

    async def stream_read(
        self,
        collection: str,
        query: Optional[Dict] = None,
        projection: Optional[List[str]] = None,
        chunk_size: int = 10_000,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        if self._session is None:
            raise RuntimeError("Cassandra session is not initialized. Call connect() first.")
        cols = ", ".join(projection) if projection else "*"
        cql = f"SELECT {cols} FROM {collection}"
        statement = self._session.prepare(cql)
        statement.fetch_size = chunk_size
        rs = self._session.execute(statement)

        buffer: List[Dict] = []
        for row in rs:
            buffer.append(row._asdict())
            if len(buffer) >= chunk_size:
                yield pa.RecordBatch.from_pylist(buffer)
                buffer = []

        if buffer:
            yield pa.RecordBatch.from_pylist(buffer)

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_write(
        self,
        collection: str,
        records: List[Dict[str, Any]],
        upsert_key: Optional[str] = None,
    ) -> None:
        if not records:
            return
        if self._session is None:
            raise RuntimeError("Cassandra session is not initialized. Call connect() first.")
        cols = list(records[0].keys())
        cols_str = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        cql = f"INSERT INTO {collection} ({cols_str}) VALUES ({placeholders})"
        stmt = self._session.prepare(cql)

        for rec in records:
            vals = [rec[c] for c in cols]
            self._session.execute(stmt, vals)
        logger.info("[Cassandra] Wrote %d records to '%s'", len(records), collection)


class DynamoConnector(BaseNoSQLConnector):
    def __init__(self, table_name: str, region_name: str = "us-east-1"):
        self.table_name = table_name
        self.region_name = region_name
        self._dynamodb = None
        self._table = None

    async def connect(self) -> None:
        import boto3
        self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._dynamodb.Table(self.table_name)
        logger.info("[DynamoDB] Connected to table '%s'", self.table_name)

    async def close(self) -> None:
        self._dynamodb = None
        self._table = None

    async def stream_read(
        self,
        collection: str,
        query: Optional[Dict] = None,
        projection: Optional[List[str]] = None,
        chunk_size: int = 10_000,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        if self._table is None:
            raise RuntimeError("DynamoDB table is not initialized. Call connect() first.")
        scan_kwargs = {}
        if projection:
            scan_kwargs["ProjectionExpression"] = ", ".join(projection)

        done = False
        start_key = None
        buffer: List[Dict] = []

        while not done:
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key
            response = self._table.scan(**scan_kwargs)
            items = response.get("Items", [])
            buffer.extend(items)

            start_key = response.get("LastEvaluatedKey")
            done = start_key is None

            while len(buffer) >= chunk_size:
                yield pa.RecordBatch.from_pylist(buffer[:chunk_size])
                buffer = buffer[chunk_size:]

        if buffer:
            yield pa.RecordBatch.from_pylist(buffer)

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_write(
        self,
        collection: str,
        records: List[Dict[str, Any]],
        upsert_key: Optional[str] = None,
    ) -> None:
        if not records:
            return
        if self._table is None:
            raise RuntimeError("DynamoDB table is not initialized. Call connect() first.")
        with self._table.batch_writer() as batch:
            for rec in records:
                batch.put_item(Item=rec)
        logger.info("[DynamoDB] Batch wrote %d items", len(records))



def create_nosql_connector(config: Dict[str, Any]) -> BaseNoSQLConnector:
    adapter = config.get("adapter") or config.get("db_type") or "mongo"
    adapter = adapter.lower()
    if adapter in ("mongo", "mongodb"):
        return MongoConnector(
            uri=config.get("connection_string", "mongodb://localhost:27017"),
            db_name=config.get("database", "etl_db"),
        )
    if adapter == "cassandra":
        return CassandraConnector(
            hosts=config.get("hosts", ["127.0.0.1"]),
            keyspace=config.get("keyspace", "etl_keyspace"),
            port=config.get("port", 9042),
        )
    if adapter == "dynamo":
        return DynamoConnector(
            table_name=config.get("table_name", "etl_table"),
            region_name=config.get("region", "us-east-1"),
        )
    raise ValueError(f"Unsupported NoSQL adapter: '{adapter}'")
