"""
veloctra_connectors/sql_connector.py
====================================
Async SQL connector supporting PostgreSQL (asyncpg), MySQL (aiomysql), and SQLite (aiosqlite).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import pyarrow as pa

from veloctra_security.secrets_manager import resolve_secret
from veloctra_resilience.retry import async_retry

logger = logging.getLogger(__name__)


def _detect_driver(connection_string: str) -> str:
    if "asyncpg" in connection_string or "postgresql" in connection_string:
        return "asyncpg"
    if "aiomysql" in connection_string or "mysql" in connection_string:
        return "aiomysql"
    if "sqlite" in connection_string:
        return "sqlite"
    raise ValueError(f"Cannot detect SQL driver from connection string: {connection_string[:40]}…")


class SQLConnector:
    def __init__(
        self,
        connection_string: str,
        pool_min: int = 2,
        pool_max: int = 10,
    ):
        raw = resolve_secret(connection_string) if connection_string.startswith("env:") else connection_string
        self._dsn = raw
        self._driver = _detect_driver(raw)
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool = None

    async def __aenter__(self) -> "SQLConnector":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._driver == "asyncpg":
            await self._connect_asyncpg()
        elif self._driver == "aiomysql":
            await self._connect_aiomysql()
        elif self._driver == "sqlite":
            await self._connect_sqlite()

    async def _connect_sqlite(self) -> None:
        import aiosqlite
        path = self._dsn.replace("sqlite:///", "").replace("sqlite://", "")
        self._sqlite_conn = await aiosqlite.connect(path)
        await self._sqlite_conn.execute("PRAGMA journal_mode = WAL;")
        await self._sqlite_conn.execute("PRAGMA synchronous = NORMAL;")
        await self._sqlite_conn.execute("PRAGMA busy_timeout = 5000;")
        await self._sqlite_conn.execute("PRAGMA cache_size = -64000;")
        await self._sqlite_conn.commit()
        logger.info("[SQL] aiosqlite connected to '%s' (WAL mode, busy_timeout=5000)", path)

    async def _connect_asyncpg(self) -> None:
        import asyncpg
        dsn = self._dsn.replace("postgresql+asyncpg://", "postgresql://")
        self._pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=self._pool_min,
            max_size=self._pool_max,
        )
        logger.info("[SQL] asyncpg pool created (min=%d, max=%d)", self._pool_min, self._pool_max)

    async def _connect_aiomysql(self) -> None:
        import aiomysql
        from urllib.parse import urlparse
        parsed = urlparse(self._dsn.replace("mysql+aiomysql://", "mysql://"))
        self._pool = await aiomysql.create_pool(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            db=parsed.path.lstrip("/"),
            minsize=self._pool_min,
            maxsize=self._pool_max,
        )
        logger.info("[SQL] aiomysql pool created (min=%d, max=%d)", self._pool_min, self._pool_max)

    async def close(self) -> None:
        if self._driver == "sqlite" and hasattr(self, "_sqlite_conn") and self._sqlite_conn:
            await self._sqlite_conn.close()
            self._sqlite_conn = None
        if self._pool is not None:
            if self._driver == "asyncpg":
                await self._pool.close()
            elif self._driver == "aiomysql":
                self._pool.close()
                await self._pool.wait_closed()
            self._pool = None
            logger.info("[SQL] Connection pool closed")

    async def stream_read(
        self,
        query: str,
        chunk_size: int = 10_000,
        watermark_clause: Optional[str] = None,
        params: Optional[Tuple] = None,
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        full_query = query.strip()
        if watermark_clause:
            if " where " in full_query.lower():
                full_query = f"{full_query} AND ({watermark_clause})"
            else:
                full_query = f"{full_query} WHERE {watermark_clause}"

        if self._driver == "asyncpg":
            async for batch in self._stream_asyncpg(full_query, chunk_size, params):
                yield batch
        elif self._driver == "aiomysql":
            async for batch in self._stream_aiomysql(full_query, chunk_size, params):
                yield batch
        elif self._driver == "sqlite":
            async for batch in self._stream_sqlite(full_query, chunk_size, params):
                yield batch

    async def _stream_sqlite(
        self, query: str, chunk_size: int, params: Optional[Tuple]
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        async with self._sqlite_conn.execute(query, params or ()) as cursor:
            columns = [col[0] for col in cursor.description]
            while True:
                rows = await cursor.fetchmany(chunk_size)
                if not rows:
                    break
                yield self._rows_to_batch(rows, columns)

    async def _stream_asyncpg(
        self, query: str, chunk_size: int, params: Optional[Tuple]
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                cursor = conn.cursor(query, *(params or []))
                columns: Optional[List[str]] = None
                buffer: List[Tuple] = []

                async for row in cursor:
                    if columns is None:
                        columns = list(row.keys())
                    buffer.append(tuple(row))
                    if len(buffer) >= chunk_size:
                        yield self._rows_to_batch(buffer, columns)
                        buffer = []

                if buffer and columns:
                    yield self._rows_to_batch(buffer, columns)

    async def _stream_aiomysql(
        self, query: str, chunk_size: int, params: Optional[Tuple]
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                while True:
                    rows = await cursor.fetchmany(chunk_size)
                    if not rows:
                        break
                    yield self._rows_to_batch(rows, columns)

    async def _get_table_types(self, conn, table_name: str) -> Dict[str, str]:
        if not hasattr(self, "_cached_table_types"):
            self._cached_table_types = {}
        if table_name not in self._cached_table_types:
            rows = await conn.fetch(
                """SELECT column_name, data_type 
                   FROM information_schema.columns 
                   WHERE table_name = $1""",
                table_name
            )
            self._cached_table_types[table_name] = {r["column_name"].lower(): r["data_type"].lower() for r in rows}
        return self._cached_table_types[table_name]

    def _coerce_records(self, batch: pa.RecordBatch, cols: List[str], col_types: Dict[str, str]) -> List[Tuple]:
        from decimal import Decimal
        coerced_rows = []
        num_cols = len(cols)
        pydict = {col: batch.column(i).to_pylist() for i, col in enumerate(cols)}
        
        for r in range(batch.num_rows):
            row_vals = []
            for col in cols:
                val = pydict[col][r]
                target_type = col_types.get(col.lower(), "")
                if val is None:
                    row_vals.append(None)
                elif "character" in target_type or "text" in target_type:
                    if isinstance(val, float) and val.is_integer():
                        row_vals.append(str(int(val)))
                    else:
                        row_vals.append(str(val))
                elif "numeric" in target_type or "decimal" in target_type:
                    row_vals.append(Decimal(str(val)))
                elif "int" in target_type:
                    row_vals.append(int(val))
                elif "double" in target_type or "real" in target_type:
                    row_vals.append(float(val))
                else:
                    row_vals.append(val)
            coerced_rows.append(tuple(row_vals))
        return coerced_rows

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_upsert(
        self,
        table_name: str,
        batch: pa.RecordBatch,
        match_keys: List[str],
    ) -> None:
        if self._driver == "sqlite":
            await self._bulk_insert_sqlite(table_name, batch)
            return

        cols = batch.schema.names
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        cols_str = ", ".join(cols)
        non_keys = [c for c in cols if c not in match_keys]

        if not non_keys:
            update_clause = "DO NOTHING"
        else:
            set_exprs = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_keys)
            update_clause = f"DO UPDATE SET {set_exprs}"

        match_str = ", ".join(match_keys)
        query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({match_str}) {update_clause}"

        if self._driver == "asyncpg":
            async with self._pool.acquire() as conn:
                col_types = await self._get_table_types(conn, table_name)
                rows = self._coerce_records(batch, cols, col_types)
                async with conn.transaction():
                    await conn.executemany(query, rows)

        logger.info("[SQL] Upserted %d rows into '%s'", batch.num_rows, table_name)

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_delete(
        self,
        table_name: str,
        batch: pa.RecordBatch,
        match_keys: List[str],
    ) -> None:
        if batch.num_rows == 0 or not match_keys:
            return
        pydict = {k: batch.column(batch.schema.get_field_index(k)).to_pylist() for k in match_keys}
        if self._driver == "sqlite":
            where_clause = " AND ".join(f"{k} = ?" for k in match_keys)
            query = f"DELETE FROM {table_name} WHERE {where_clause}"
            rows = [tuple(pydict[k][r] for k in match_keys) for r in range(batch.num_rows)]
            await self._sqlite_conn.executemany(query, rows)
            await self._sqlite_conn.commit()
        elif self._driver == "asyncpg":
            where_clause = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(match_keys))
            query = f"DELETE FROM {table_name} WHERE {where_clause}"
            rows = [tuple(pydict[k][r] for k in match_keys) for r in range(batch.num_rows)]
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany(query, rows)
        logger.info("[SQL] Deleted %d rows from '%s' via CDC", batch.num_rows, table_name)

    async def _bulk_insert_sqlite(self, table_name: str, batch: pa.RecordBatch) -> None:
        cols = batch.schema.names
        cols_str = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        query = f"INSERT OR REPLACE INTO {table_name} ({cols_str}) VALUES ({placeholders})"
        rows = [tuple(batch.column(i)[r].as_py() for i in range(batch.num_columns)) for r in range(batch.num_rows)]
        await self._sqlite_conn.executemany(query, rows)
        await self._sqlite_conn.commit()

    @async_retry(max_attempts=3, initial_backoff=1.0)
    async def bulk_insert(self, table_name: str, batch: pa.RecordBatch) -> None:
        if self._driver == "sqlite":
            await self._bulk_insert_sqlite(table_name, batch)
            return
        cols = batch.schema.names

        if self._driver == "asyncpg":
            async with self._pool.acquire() as conn:
                col_types = await self._get_table_types(conn, table_name)
                rows = self._coerce_records(batch, cols, col_types)
                try:
                    await conn.copy_records_to_table(table_name, records=rows, columns=cols)
                except Exception:
                    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
                    query = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
                    async with conn.transaction():
                        await conn.executemany(query, rows)

        logger.info("[SQL] Inserted %d rows into '%s'", batch.num_rows, table_name)

    def _rows_to_batch(self, rows: List[Tuple], columns: List[str]) -> pa.RecordBatch:
        pydict = {col: [row[i] for row in rows] for i, col in enumerate(columns)}
        return pa.RecordBatch.from_pydict(pydict)
