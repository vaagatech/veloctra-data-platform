"""
veloctra_state/state_store.py
=============================
Pluggable Async State Store with SQLite (WAL mode) and MongoDB Adapters.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite
import motor.motor_asyncio

from veloctra_core.settings import get_settings
from veloctra_security.security import sanitize_config, EncryptionService

logger = logging.getLogger(__name__)
settings = get_settings()

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    state TEXT NOT NULL,
    rows_written INTEGER DEFAULT 0,
    watermark_value TEXT,
    created_at REAL NOT NULL,
    UNIQUE(job_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS dlq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    row_payload TEXT NOT NULL,
    error_trace TEXT NOT NULL,
    chunk_index INTEGER,
    replayed INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fsm_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    metadata TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    config_payload TEXT NOT NULL,
    active INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    UNIQUE(project_id, tenant_id, version)
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tenant_id TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT,
    config_payload TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class BaseStateAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def save_checkpoint(
        self,
        job_id: str,
        tenant_id: str,
        chunk_index: int,
        state: str,
        rows_written: int = 0,
        watermark_value: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    async def get_latest_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_resume_chunk(self, job_id: str) -> int:
        pass

    @abstractmethod
    async def get_last_watermark(self, job_id: str, pipeline_id: Optional[str] = None) -> Optional[str]:
        pass

    @abstractmethod
    async def push_dlq(
        self,
        job_id: str,
        tenant_id: str,
        row_payload: Dict[str, Any],
        error_trace: str,
        chunk_index: Optional[int] = None,
    ) -> Any:
        pass


    @abstractmethod
    async def get_dlq_records(
        self,
        job_id: str,
        include_replayed: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def mark_dlq_replayed(self, record_id: int) -> None:
        pass

    @abstractmethod
    async def log_fsm_transition(
        self,
        job_id: str,
        tenant_id: str,
        from_state: str,
        to_state: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        pass

    @abstractmethod
    async def get_audit_events(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def save_pipeline_config(self, tenant_id: str, project_id: str, config: Dict[str, Any]) -> int:
        pass

    @abstractmethod
    async def get_pipeline_config(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_pipeline_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_pipeline_versions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def save_project(self, tenant_id: str, proj_id: str, name: str, description: str) -> None:
        pass

    @abstractmethod
    async def get_projects(self, tenant_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def save_connection(self, tenant_id: str, conn_id: str, name: str, type: str, url: str, config_payload: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def get_connections(self, tenant_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_all_job_states(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        pass

    @abstractmethod
    async def get_all_job_details(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_next_run_id(self, tenant_id: str, pipeline_id: str) -> str:
        pass


class SQLiteStateAdapter(BaseStateAdapter):
    _shared_conn: Optional[aiosqlite.Connection] = None
    _init_lock: Optional[asyncio.Lock] = None

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = Path(db_path or settings.state_db_path)

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._init_lock is None:
            cls._init_lock = asyncio.Lock()
        return cls._init_lock

    async def connect(self) -> None:
        async with self._get_lock():
            if SQLiteStateAdapter._shared_conn is None:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = await aiosqlite.connect(str(self._db_path), timeout=30.0)
                conn.row_factory = aiosqlite.Row
                try:
                    await conn.execute("PRAGMA journal_mode = WAL;")
                    await conn.execute("PRAGMA synchronous = NORMAL;")
                    await conn.execute("PRAGMA busy_timeout = 10000;")
                except Exception:
                    pass
                await conn.executescript(_SQLITE_DDL)
                await conn.commit()
                SQLiteStateAdapter._shared_conn = conn
                logger.info("[StateStore:SQLite] Shared connection established to '%s' (WAL mode)", self._db_path)

    async def close(self) -> None:
        async with self._get_lock():
            if SQLiteStateAdapter._shared_conn:
                await SQLiteStateAdapter._shared_conn.close()
                SQLiteStateAdapter._shared_conn = None
                logger.info("[StateStore:SQLite] Shared connection closed")

    async def _ensure_conn(self) -> aiosqlite.Connection:
        if SQLiteStateAdapter._shared_conn is None:
            await self.connect()
        assert SQLiteStateAdapter._shared_conn is not None
        return SQLiteStateAdapter._shared_conn

    async def save_checkpoint(
        self,
        job_id: str,
        tenant_id: str,
        chunk_index: int,
        state: str,
        rows_written: int = 0,
        watermark_value: Optional[str] = None,
    ) -> None:
        conn = await self._ensure_conn()
        now = time.time()
        sql = """
            INSERT INTO checkpoints
                (job_id, tenant_id, chunk_index, state, rows_written, watermark_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, chunk_index) DO UPDATE SET
                state = excluded.state,
                rows_written = excluded.rows_written,
                watermark_value = excluded.watermark_value,
                created_at = excluded.created_at
        """
        await conn.execute(sql, (job_id, tenant_id, chunk_index, state, rows_written, watermark_value, now))
        await conn.commit()

    async def get_latest_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        conn = await self._ensure_conn()
        sql = "SELECT * FROM checkpoints WHERE job_id = ? ORDER BY chunk_index DESC LIMIT 1"
        async with conn.execute(sql, (job_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_resume_chunk(self, job_id: str) -> int:
        cp = await self.get_latest_checkpoint(job_id)
        if cp is None or cp.get("state") != "COMPLETED":
            return 0
        return cp["chunk_index"] + 1

    async def get_last_watermark(self, job_id: str, pipeline_id: Optional[str] = None) -> Optional[str]:
        conn = await self._ensure_conn()
        if pipeline_id:
            sql = """
                SELECT watermark_value FROM checkpoints 
                WHERE (job_id = ? OR job_id LIKE ?) AND watermark_value IS NOT NULL AND watermark_value != ''
                ORDER BY created_at DESC, chunk_index DESC LIMIT 1
            """
            async with conn.execute(sql, (job_id, f"{pipeline_id}_%")) as cursor:
                row = await cursor.fetchone()
                return str(row["watermark_value"]) if row and row["watermark_value"] else None
        else:
            sql = """
                SELECT watermark_value FROM checkpoints 
                WHERE job_id = ? AND watermark_value IS NOT NULL AND watermark_value != ''
                ORDER BY chunk_index DESC LIMIT 1
            """
            async with conn.execute(sql, (job_id,)) as cursor:
                row = await cursor.fetchone()
                return str(row["watermark_value"]) if row and row["watermark_value"] else None

    async def push_dlq(
        self,
        job_id: str,
        tenant_id: str,
        row_payload: Dict[str, Any],
        error_trace: str,
        chunk_index: Optional[int] = None,
    ) -> Any:

        conn = await self._ensure_conn()
        now = time.time()
        payload_str = json.dumps(sanitize_config(row_payload), default=str)
        sql = """
            INSERT INTO dlq (job_id, tenant_id, row_payload, error_trace, chunk_index, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = await conn.execute(sql, (job_id, tenant_id, payload_str, error_trace, chunk_index, now))
        await conn.commit()
        return cursor.lastrowid or 0


    async def get_dlq_records(
        self,
        job_id: str,
        include_replayed: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        sql = "SELECT * FROM dlq WHERE job_id = ?"
        params: list = [job_id]
        if not include_replayed:
            sql += " AND replayed = 0"
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)

        async with conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["row_payload"] = json.loads(d["row_payload"])
                except Exception:
                    pass
                d["replayed"] = bool(d["replayed"])
                result.append(d)
            return result

    async def mark_dlq_replayed(self, record_id: int) -> None:
        conn = await self._ensure_conn()
        await conn.execute("UPDATE dlq SET replayed = 1 WHERE id = ?", (record_id,))
        await conn.commit()

    async def log_fsm_transition(
        self,
        job_id: str,
        tenant_id: str,
        from_state: str,
        to_state: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        conn = await self._ensure_conn()
        now = time.time()
        meta_str = json.dumps(sanitize_config(metadata or {}))
        sql = """
            INSERT INTO fsm_events (job_id, tenant_id, from_state, to_state, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        await conn.execute(sql, (job_id, tenant_id, from_state, to_state, meta_str, now))
        await conn.commit()

    async def get_audit_events(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        sql = "SELECT * FROM fsm_events WHERE job_id = ? ORDER BY id DESC LIMIT ?"
        async with conn.execute(sql, (job_id, limit)) as cursor:
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except Exception:
                    pass
                result.append(d)
            return result
            return result

    async def save_pipeline_config(self, tenant_id: str, project_id: str, config: Dict[str, Any]) -> int:
        conn = await self._ensure_conn()
        now = time.time()
        
        await conn.execute(
            "UPDATE pipeline_configs SET active = 0 WHERE project_id = ? AND tenant_id = ?",
            (project_id, tenant_id)
        )
        
        cursor = await conn.execute(
            "SELECT MAX(version) FROM pipeline_configs WHERE project_id = ? AND tenant_id = ?",
            (project_id, tenant_id)
        )
        row = await cursor.fetchone()
        next_version = (row[0] or 0) + 1
        
        config_str = json.dumps(config)
        await conn.execute(
            """INSERT INTO pipeline_configs (project_id, tenant_id, version, config_payload, active, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (project_id, tenant_id, next_version, config_str, now)
        )
        await conn.commit()
        return next_version

    async def get_pipeline_config(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        conn = await self._ensure_conn()
        if version is not None:
            cursor = await conn.execute(
                "SELECT config_payload FROM pipeline_configs WHERE project_id = ? AND tenant_id = ? AND version = ?",
                (project_id, tenant_id, version)
            )
        else:
            cursor = await conn.execute(
                "SELECT config_payload FROM pipeline_configs WHERE project_id = ? AND tenant_id = ? AND active = 1 ORDER BY version DESC LIMIT 1",
                (project_id, tenant_id)
            )
        row = await cursor.fetchone()
        if row:
            return json.loads(row["config_payload"])
        return None

    async def get_pipeline_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT project_id, version, config_payload, active, created_at FROM pipeline_configs WHERE tenant_id = ?",
            (tenant_id,)
        )
        rows = await cursor.fetchall()
        return [
            {
                "project_id": r["project_id"],
                "version": r["version"],
                "active": bool(r["active"]),
                "created_at": r["created_at"],
                "config": json.loads(r["config_payload"])
            }
            for r in rows
        ]

    async def get_pipeline_versions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT project_id, version, active, created_at FROM pipeline_configs WHERE tenant_id = ? AND project_id = ? ORDER BY version DESC",
            (tenant_id, project_id)
        )
        rows = await cursor.fetchall()
        return [
            {
                "project_id": r["project_id"],
                "version": r["version"],
                "active": bool(r["active"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


    async def get_next_run_id(self, tenant_id: str, pipeline_id: str) -> str:
        conn = await self._ensure_conn()
        prefix = f"{pipeline_id}_"
        cursor = await conn.execute(
            "SELECT COUNT(DISTINCT job_id) FROM fsm_events WHERE tenant_id = ? AND job_id LIKE ?",
            (tenant_id, f"{prefix}%")
        )
        row = await cursor.fetchone()
        count = row[0] or 0
        return f"{pipeline_id}_{count + 1}"

    async def save_project(self, tenant_id: str, proj_id: str, name: str, description: str) -> None:
        conn = await self._ensure_conn()
        now = time.time()
        await conn.execute(
            """INSERT INTO projects (id, name, description, tenant_id, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, description=excluded.description""",
            (proj_id, name, description, tenant_id, now)
        )
        await conn.commit()

    async def get_projects(self, tenant_id: str) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        if tenant_id in ("*", "", None):
            cursor = await conn.execute("SELECT id, name, description, created_at FROM projects")
        else:
            cursor = await conn.execute(
                "SELECT id, name, description, created_at FROM projects WHERE tenant_id = ?",
                (tenant_id,)
            )
        rows = await cursor.fetchall()
        return [{"id": r["id"], "name": r["name"], "description": r["description"], "created_at": r["created_at"]} for r in rows]

    async def save_connection(self, tenant_id: str, conn_id: str, name: str, type: str, url: str, config_payload: Dict[str, Any]) -> None:
        conn = await self._ensure_conn()
        now = time.time()
        config_str = json.dumps(config_payload)
        await conn.execute(
            """INSERT INTO connections (id, name, type, url, config_payload, tenant_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type, url=excluded.url, config_payload=excluded.config_payload""",
            (conn_id, name, type, url, config_str, tenant_id, now)
        )
        await conn.commit()

    async def get_connections(self, tenant_id: str) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        cursor = await conn.execute(
            "SELECT id, name, type, url, config_payload, created_at FROM connections WHERE tenant_id = ?",
            (tenant_id,)
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "url": r["url"],
                "config_payload": json.loads(r["config_payload"]),
                "created_at": r["created_at"]
            }
            for r in rows
        ]

    async def get_all_job_states(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        conn = await self._ensure_conn()
        if tenant_id and tenant_id not in ("*", "", None):
            cursor = await conn.execute(
                """SELECT e1.job_id, e1.to_state FROM fsm_events e1
                   INNER JOIN (
                       SELECT job_id, MAX(created_at) as max_created FROM fsm_events WHERE tenant_id = ? GROUP BY job_id
                   ) e2 ON e1.job_id = e2.job_id AND e1.created_at = e2.max_created""",
                (tenant_id,)
            )
        else:
            cursor = await conn.execute(
                """SELECT e1.job_id, e1.to_state FROM fsm_events e1
                   INNER JOIN (
                       SELECT job_id, MAX(created_at) as max_created FROM fsm_events GROUP BY job_id
                   ) e2 ON e1.job_id = e2.job_id AND e1.created_at = e2.max_created"""
            )
        rows = await cursor.fetchall()
        return {r["job_id"]: r["to_state"] for r in rows}

    async def get_all_job_details(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._ensure_conn()
        if tenant_id and tenant_id not in ("*", "", None):
            cursor = await conn.execute(
                """SELECT job_id, 
                          MIN(created_at) as created_at, 
                          MAX(created_at) as updated_at,
                          tenant_id
                   FROM fsm_events WHERE tenant_id = ? GROUP BY job_id ORDER BY created_at DESC""",
                (tenant_id,)
            )
        else:
            cursor = await conn.execute(
                """SELECT job_id, 
                          MIN(created_at) as created_at, 
                          MAX(created_at) as updated_at,
                          tenant_id
                   FROM fsm_events GROUP BY job_id ORDER BY created_at DESC"""
            )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            jid = r["job_id"]
            c2 = await conn.execute("SELECT to_state FROM fsm_events WHERE job_id = ? ORDER BY created_at DESC LIMIT 1", (jid,))
            row_state = await c2.fetchone()
            state = row_state["to_state"] if row_state else "COMPLETED"
            start_ts = r["created_at"] or 0
            end_ts = r["updated_at"] or start_ts
            duration = max(0.0, round(end_ts - start_ts, 2))
            parts = jid.rsplit("_", 1)
            pipeline_name = parts[0] if len(parts) > 1 and parts[1].isdigit() else jid
            results.append({
                "id": jid,
                "pipeline_id": pipeline_name,
                "state": state,
                "tenant_id": r["tenant_id"],
                "created_at": start_ts,
                "updated_at": end_ts,
                "duration_sec": duration,
            })
        return results

class MongoStateAdapter(BaseStateAdapter):
    """Async MongoDB state adapter using Motor for enterprise state management."""

    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None):
        self._uri = mongo_uri or getattr(settings, "mongo_uri", "mongodb://localhost:27017")
        self._db_name = db_name or getattr(settings, "mongo_system_db", "veloctra_system")
        self._client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self._db = None

    async def connect(self) -> None:
        self._client = motor.motor_asyncio.AsyncIOMotorClient(self._uri, serverSelectionTimeoutMS=2000)
        self._db = self._client[self._db_name]
        logger.info("[StateStore:MongoDB] Connected to '%s' database '%s'", self._uri, self._db_name)

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            logger.info("[StateStore:MongoDB] Connection closed")

    async def _ensure_db(self):
        if self._db is None or self._client is None:
            await self.connect()
        assert self._db is not None
        return self._db

    async def save_checkpoint(
        self,
        job_id: str,
        tenant_id: str,
        chunk_index: int,
        state: str,
        rows_written: int = 0,
        watermark_value: Optional[str] = None,
    ) -> None:
        db = await self._ensure_db()
        now = time.time()
        filter_spec = {"job_id": job_id, "chunk_index": chunk_index}
        update_doc = {
            "$set": {
                "tenant_id": tenant_id,
                "state": state,
                "rows_written": rows_written,
                "watermark_value": watermark_value,
                "created_at": now,
            }
        }
        await db.checkpoints.update_one(filter_spec, update_doc, upsert=True)

    async def get_latest_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        db = await self._ensure_db()
        doc = await db.checkpoints.find_one({"job_id": job_id}, sort=[("chunk_index", -1)])
        if doc:
            doc["id"] = str(doc.get("_id"))
            doc.pop("_id", None)
        return doc

    async def get_resume_chunk(self, job_id: str) -> int:
        cp = await self.get_latest_checkpoint(job_id)
        if cp is None or cp.get("state") != "COMPLETED":
            return 0
        return cp["chunk_index"] + 1

    async def get_last_watermark(self, job_id: str, pipeline_id: Optional[str] = None) -> Optional[str]:
        db = await self._ensure_db()
        filter_spec: Dict[str, Any] = {
            "watermark_value": {"$ne": None, "$exists": True}
        }
        if pipeline_id:
            filter_spec["$or"] = [
                {"job_id": job_id},
                {"job_id": {"$regex": f"^{pipeline_id}_"}}
            ]
        else:
            filter_spec["job_id"] = job_id
            
        doc = await db.checkpoints.find_one(filter_spec, sort=[("created_at", -1), ("chunk_index", -1)])
        if doc and doc.get("watermark_value"):
            return str(doc["watermark_value"])
        return None

    async def push_dlq(
        self,
        job_id: str,
        tenant_id: str,
        row_payload: Dict[str, Any],
        error_trace: str,
        chunk_index: Optional[int] = None,
    ) -> Any:
        db = await self._ensure_db()
        now = time.time()
        
        def _clean_val(v):
            from decimal import Decimal
            if isinstance(v, dict):
                return {k: _clean_val(val) for k, val in v.items()}
            elif isinstance(v, list):
                return [_clean_val(val) for val in v]
            elif isinstance(v, Decimal):
                return str(v)
            return v

        cleaned_payload = _clean_val(sanitize_config(row_payload))
        doc = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "row_payload": cleaned_payload,
            "error_trace": error_trace,
            "chunk_index": chunk_index,
            "replayed": False,
            "created_at": now,
        }
        res = await db.dlq.insert_one(doc)
        return str(res.inserted_id)

    async def get_dlq_records(
        self,
        job_id: str,
        include_replayed: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        filter_spec: dict = {"job_id": job_id}
        if not include_replayed:
            filter_spec["replayed"] = False

        cursor = db.dlq.find(filter_spec).sort("created_at", 1).limit(limit)
        records = []
        async for doc in cursor:
            doc["id"] = str(doc.get("_id"))
            doc.pop("_id", None)
            records.append(doc)
        return records

    async def mark_dlq_replayed(self, record_id: Any) -> None:
        db = await self._ensure_db()
        from bson import ObjectId
        try:
            filter_spec = {"_id": ObjectId(str(record_id))}
        except Exception:
            filter_spec = {"_id": record_id}

        await db.dlq.update_one(filter_spec, {"$set": {"replayed": True}})

    async def log_fsm_transition(
        self,
        job_id: str,
        tenant_id: str,
        from_state: str,
        to_state: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        db = await self._ensure_db()
        now = time.time()
        doc = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "from_state": from_state,
            "to_state": to_state,
            "metadata": sanitize_config(metadata or {}),
            "created_at": now,
        }
        await db.fsm_events.insert_one(doc)

    async def get_audit_events(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        cursor = db.fsm_events.find({"job_id": job_id}).sort("created_at", -1).limit(limit)
        events = []
        async for doc in cursor:
            doc["id"] = str(doc.get("_id"))
            doc.pop("_id", None)
            events.append(doc)
        return events

    async def get_all_job_states(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        db = await self._ensure_db()
        match_stage = {"tenant_id": tenant_id} if tenant_id and tenant_id not in ("*", "", None) else {}
        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$job_id",
                "latest_state": {"$first": "$to_state"},
                "tenant_id": {"$first": "$tenant_id"},
                "last_updated": {"$first": "$created_at"}
            }}
        ]
        results = {}
        async for doc in db.fsm_events.aggregate(pipeline):
            results[doc["_id"]] = doc["latest_state"]
        return results

    async def get_all_job_details(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        match_stage = {"tenant_id": tenant_id} if tenant_id and tenant_id not in ("*", "", None) else {}
        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$sort": {"created_at": 1}},
            {"$group": {
                "_id": "$job_id",
                "latest_state": {"$last": "$to_state"},
                "tenant_id": {"$last": "$tenant_id"},
                "created_at": {"$first": "$created_at"},
                "updated_at": {"$last": "$created_at"},
            }},
            {"$sort": {"created_at": -1}}
        ]
        results = []
        async for doc in db.fsm_events.aggregate(pipeline):
            jid = doc["_id"]
            start_ts = doc.get("created_at") or 0
            end_ts = doc.get("updated_at") or start_ts
            duration = max(0.0, round(end_ts - start_ts, 2))
            parts = jid.rsplit("_", 1)
            pipeline_name = parts[0] if len(parts) > 1 and parts[1].isdigit() else jid
            results.append({
                "id": jid,
                "pipeline_id": pipeline_name,
                "state": doc.get("latest_state", "COMPLETED"),
                "tenant_id": doc.get("tenant_id", tenant_id),
                "created_at": start_ts,
                "updated_at": end_ts,
                "duration_sec": duration,
            })
        return results

    async def get_connections(self, tenant_id: str) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        cursor = db.connections.find({"tenant_id": tenant_id})
        conns = []
        async for doc in cursor:
            conns.append({
                "id": doc.get("id") or str(doc.get("_id")),
                "name": doc.get("name", ""),
                "type": doc.get("type", ""),
                "url": doc.get("url", ""),
                "config_payload": doc.get("config_payload", {}),
                "tenant_id": doc.get("tenant_id", tenant_id),
                "created_at": doc.get("created_at", time.time()),
            })
        return conns

    async def save_connection(self, tenant_id: str, conn_id: str, name: str, type: str, url: str, config_payload: Dict[str, Any]) -> None:
        db = await self._ensure_db()
        now = time.time()
        await db.connections.update_one(
            {"id": conn_id, "tenant_id": tenant_id},
            {"$set": {"name": name, "type": type, "url": url, "config_payload": config_payload, "created_at": now}},
            upsert=True,
        )

    async def save_project(self, tenant_id: str, proj_id: str, name: str, description: str) -> None:
        db = await self._ensure_db()
        now = time.time()
        await db.projects.update_one(
            {"id": proj_id, "tenant_id": tenant_id},
            {"$set": {"name": name, "description": description, "created_at": now}},
            upsert=True,
        )

    async def get_projects(self, tenant_id: str) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        filter_spec = {} if tenant_id in ("*", "", None) else {"tenant_id": tenant_id}
        cursor = db.projects.find(filter_spec)
        res = []
        async for doc in cursor:
            doc["id"] = doc.get("id") or str(doc.get("_id"))
            doc.pop("_id", None)
            res.append(doc)
        return res

    async def save_pipeline_config(self, tenant_id: str, project_id: str, config: Dict[str, Any]) -> int:
        db = await self._ensure_db()
        now = time.time()
        await db.pipeline_configs.update_many(
            {"project_id": project_id, "tenant_id": tenant_id},
            {"$set": {"active": 0}},
        )
        latest = await db.pipeline_configs.find_one(
            {"project_id": project_id, "tenant_id": tenant_id},
            sort=[("version", -1)],
        )
        next_version = (latest.get("version", 0) if latest else 0) + 1
        doc = {
            "project_id": project_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "config_payload": json.dumps(config) if isinstance(config, dict) else config,
            "active": 1,
            "created_at": now,
        }
        await db.pipeline_configs.insert_one(doc)
        return next_version

    async def get_pipeline_config(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        db = await self._ensure_db()
        filter_spec: Dict[str, Any] = {"project_id": project_id, "tenant_id": tenant_id}
        if version is not None:
            filter_spec["version"] = version
        else:
            filter_spec["active"] = 1
        doc = await db.pipeline_configs.find_one(filter_spec, sort=[("version", -1)])
        if doc and "config_payload" in doc:
            raw = doc["config_payload"]
            return json.loads(raw) if isinstance(raw, str) else raw
        return None

    async def get_pipeline_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        cursor = db.pipeline_configs.find({"tenant_id": tenant_id})
        res = []
        async for doc in cursor:
            raw = doc.get("config_payload")
            cfg = json.loads(raw) if isinstance(raw, str) else raw
            res.append({
                "project_id": doc.get("project_id"),
                "version": doc.get("version"),
                "active": bool(doc.get("active")),
                "created_at": doc.get("created_at"),
                "config": cfg,
            })
        return res

    async def get_pipeline_versions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        db = await self._ensure_db()
        cursor = db.pipeline_configs.find({"tenant_id": tenant_id, "project_id": project_id}).sort("version", -1)
        res = []
        async for doc in cursor:
            res.append({
                "project_id": doc.get("project_id"),
                "version": doc.get("version"),
                "active": bool(doc.get("active")),
                "created_at": doc.get("created_at"),
            })
        return res

    async def delete_pipeline_config(self, tenant_id: str, project_id: str) -> bool:
        db = await self._ensure_db()
        result = await db.pipeline_configs.delete_many({"tenant_id": tenant_id, "project_id": project_id})
        return result.deleted_count > 0

    async def get_next_run_id(self, tenant_id: str, pipeline_id: str) -> str:
        db = await self._ensure_db()
        prefix = f"{pipeline_id}_"
        pipeline_jobs = await db.fsm_events.distinct("job_id", {"tenant_id": tenant_id, "job_id": {"$regex": f"^{prefix}"}})
        count = len(pipeline_jobs)
        return f"{pipeline_id}_{count + 1}"

class StateStore:
    """Unified Facade delegating to configured State Adapter (MongoDB or SQLite)."""

    def __init__(self, adapter_type: Optional[str] = None, **kwargs):
        store_type = adapter_type or getattr(settings, "state_store_type", "mongodb").lower()
        if store_type in ("mongo", "mongodb"):
            mongo_uri = kwargs.get("mongo_uri") or getattr(settings, "mongo_uri", "mongodb://localhost:27017")
            db_name = kwargs.get("db_name") or getattr(settings, "mongo_system_db", "veloctra_system")
            self._adapter: BaseStateAdapter = MongoStateAdapter(mongo_uri=mongo_uri, db_name=db_name)
        else:
            self._adapter: BaseStateAdapter = SQLiteStateAdapter(db_path=kwargs.get("db_path"))
        
        self._enc_svc = EncryptionService()

    async def connect(self) -> None:
        await self._adapter.connect()

    async def close(self) -> None:
        await self._adapter.close()

    async def save_checkpoint(self, *args, **kwargs) -> None:
        await self._adapter.save_checkpoint(*args, **kwargs)

    async def get_latest_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self._adapter.get_latest_checkpoint(job_id)

    async def get_resume_chunk(self, job_id: str) -> int:
        return await self._adapter.get_resume_chunk(job_id)

    async def get_last_watermark(self, job_id: str, pipeline_id: Optional[str] = None) -> Optional[str]:
        return await self._adapter.get_last_watermark(job_id, pipeline_id)

    async def push_dlq(self, *args, **kwargs) -> Any:
        return await self._adapter.push_dlq(*args, **kwargs)

    async def get_dlq_records(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return await self._adapter.get_dlq_records(*args, **kwargs)

    async def mark_dlq_replayed(self, record_id: Any) -> None:
        await self._adapter.mark_dlq_replayed(record_id)

    async def log_fsm_transition(self, *args, **kwargs) -> None:
        await self._adapter.log_fsm_transition(*args, **kwargs)

    async def get_audit_events(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return await self._adapter.get_audit_events(*args, **kwargs)

    async def get_job_event_log(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return await self._adapter.get_audit_events(job_id, limit)

    async def save_pipeline_config(self, tenant_id: str, project_id: str, config: Dict[str, Any]) -> int:
        return await self._adapter.save_pipeline_config(tenant_id, project_id, config)

    async def get_pipeline_config(self, tenant_id: str, project_id: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return await self._adapter.get_pipeline_config(tenant_id, project_id, version)

    async def get_pipeline_configs(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self._adapter.get_pipeline_configs(tenant_id)

    async def get_pipeline_versions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        return await self._adapter.get_pipeline_versions(tenant_id, project_id)

    async def delete_pipeline_config(self, tenant_id: str, project_id: str) -> bool:
        return await self._adapter.delete_pipeline_config(tenant_id, project_id)

    async def save_project(self, tenant_id: str, proj_id: str, name: str, description: str) -> None:
        await self._adapter.save_project(tenant_id, proj_id, name, description)

    async def get_projects(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self._adapter.get_projects(tenant_id)

    async def get_next_run_id(self, tenant_id: str, pipeline_id: str) -> str:
        return await self._adapter.get_next_run_id(tenant_id, pipeline_id)

    async def get_all_job_states(self, tenant_id: Optional[str] = None) -> Dict[str, str]:
        return await self._adapter.get_all_job_states(tenant_id)

    async def get_all_job_details(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._adapter.get_all_job_details(tenant_id)

    async def save_connection(self, tenant_id: str, conn_id: str, name: str, type: str, url: str, config_payload: Dict[str, Any]) -> None:
        enc_url = self._enc_svc.encrypt_string(url) if url else url
        enc_config = self._enc_svc.encrypt_dict(config_payload)
        # Store encrypted payload as a dict wrapping the token, because adapter expects a dict to JSON serialize, or we can just pass a dict with {"_enc": token}
        enc_payload_dict = {"_enc_token": enc_config}
        await self._adapter.save_connection(tenant_id, conn_id, name, type, enc_url, enc_payload_dict)

    async def get_connections(self, tenant_id: str) -> List[Dict[str, Any]]:
        conns = await self._adapter.get_connections(tenant_id)
        for conn in conns:
            if conn.get("url"):
                try:
                    conn["url"] = self._enc_svc.decrypt_string(conn["url"])
                except Exception:
                    pass # Legacy unencrypted or error
            if isinstance(conn.get("config_payload"), dict) and "_enc_token" in conn["config_payload"]:
                try:
                    conn["config_payload"] = self._enc_svc.decrypt_dict(conn["config_payload"]["_enc_token"])
                except Exception:
                    pass
        return conns
