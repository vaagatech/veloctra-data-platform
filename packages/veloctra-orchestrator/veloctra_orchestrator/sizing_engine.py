"""
veloctra_orchestrator/sizing_engine.py
======================================
Intelligent Migration Sizing Engine & KEDA Autoscaling Planner.

Discovers workload volume (row counts, payload sizes, watermark deltas) across
SQL, NoSQL, Files, and Streams, computes optimal shard partitions, and calculates
target pod replica recommendations for Kubernetes Event-Driven Autoscaling (KEDA).
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from veloctra_connectors.sql_connector import SQLConnector
from veloctra_connectors.nosql_connector import create_nosql_connector
from veloctra_security.secrets_manager import resolve_secret

logger = logging.getLogger(__name__)


@dataclass
class SourceSizeEstimate:
    source_name: str
    source_type: str
    row_count: int
    estimated_bytes: int
    estimated_mb: float
    is_exact: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationScalingPlan:
    pipeline_id: str
    tenant_id: str
    total_rows: int
    estimated_payload_mb: float
    recommended_replicas: int
    recommended_shards: int
    rows_per_worker: int
    min_replicas: int
    max_replicas: int
    keda_enabled: bool
    sources: List[SourceSizeEstimate] = field(default_factory=list)
    shard_intervals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "tenant_id": self.tenant_id,
            "total_rows": self.total_rows,
            "estimated_payload_mb": round(self.estimated_payload_mb, 2),
            "recommended_replicas": self.recommended_replicas,
            "recommended_shards": self.recommended_shards,
            "rows_per_worker": self.rows_per_worker,
            "min_replicas": self.min_replicas,
            "max_replicas": self.max_replicas,
            "keda_enabled": self.keda_enabled,
            "sources": [
                {
                    "source_name": s.source_name,
                    "source_type": s.source_type,
                    "row_count": s.row_count,
                    "estimated_mb": round(s.estimated_mb, 2),
                    "is_exact": s.is_exact,
                    "details": s.details,
                }
                for s in self.sources
            ],
            "shard_intervals": self.shard_intervals,
        }


class MigrationSizingEngine:
    """
    Analyzes migration volume across diverse data sources and computes
    intelligent KEDA scaling recommendations and process shard partitions.
    """

    def __init__(
        self,
        default_rows_per_worker: int = 100_000,
        default_min_replicas: int = 1,
        default_max_replicas: int = 16,
        default_avg_row_bytes: int = 500,
    ):
        self.default_rows_per_worker = default_rows_per_worker
        self.default_min_replicas = default_min_replicas
        self.default_max_replicas = default_max_replicas
        self.default_avg_row_bytes = default_avg_row_bytes

    async def estimate_source(
        self,
        src: Dict[str, Any],
        active_watermark: Optional[Any] = None,
    ) -> SourceSizeEstimate:
        stype = src.get("type", "database").lower()
        sname = src.get("name", "source")

        if stype in ("database", "sql", "postgres", "postgresql", "mysql", "sqlite"):
            return await self._estimate_sql_source(src, active_watermark)
        elif stype in ("nosql", "mongodb", "mongo"):
            return await self._estimate_nosql_source(src, active_watermark)
        elif stype in ("file", "csv", "parquet", "zip"):
            return await self._estimate_file_source(src)
        else:
            # Fallback estimation
            return SourceSizeEstimate(
                source_name=sname,
                source_type=stype,
                row_count=10_000,
                estimated_bytes=10_000 * self.default_avg_row_bytes,
                estimated_mb=(10_000 * self.default_avg_row_bytes) / (1024 * 1024),
                is_exact=False,
                details={"note": "Default heuristic estimation for non-relational source"},
            )

    async def _estimate_sql_source(
        self,
        src: Dict[str, Any],
        active_watermark: Optional[Any] = None,
    ) -> SourceSizeEstimate:
        conn_str = src.get("connection_string", "")
        raw_query = src.get("query", "")
        delta_cfg = src.get("delta", {}) or {}
        wm_col = delta_cfg.get("watermark_column") or src.get("watermark_column")
        wm_type = delta_cfg.get("watermark_type", "timestamp").lower()
        init_wm = delta_cfg.get("initial_watermark")
        effective_wm = active_watermark if active_watermark is not None else init_wm

        wm_clause = None
        if wm_col and effective_wm is not None:
            if wm_type in ("int", "integer", "bigint", "float", "numeric", "number"):
                wm_clause = f"{wm_col} > {effective_wm}"
            else:
                safe_val = str(effective_wm).replace("'", "''")
                wm_clause = f"{wm_col} > '{safe_val}'"

        row_count = 0
        is_exact = False
        details = {}

        try:
            async with SQLConnector(conn_str) as conn:
                # 1. Check if direct table extraction (SELECT * FROM table)
                match = re.search(r"from\s+([a-zA-Z0-9_\.\"]+)", raw_query, re.IGNORECASE)
                table_name = match.group(1).strip('"') if match else None

                if conn._driver == "sqlite" and conn._sqlite_conn:
                    if wm_clause and table_name:
                        count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {wm_clause}"
                    elif table_name:
                        count_sql = f"SELECT COUNT(*) FROM {table_name}"
                    else:
                        count_sql = f"SELECT COUNT(*) FROM ({raw_query}) AS _subq"
                    
                    cursor = await conn._sqlite_conn.execute(count_sql)
                    row = await cursor.fetchone()
                    if row:
                        row_count = int(row[0])
                        is_exact = True
                        details["count_sql"] = count_sql

                elif conn._driver == "asyncpg" and conn._pool:
                    async with conn._pool.acquire() as pg_conn:
                        if wm_clause and table_name:
                            count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {wm_clause}"
                        elif table_name and not wm_clause:
                            # Try fast catalog estimation first
                            fast_est = await pg_conn.fetchval(
                                "SELECT reltuples::bigint FROM pg_class WHERE relname = $1",
                                table_name,
                            )
                            if fast_est is not None and fast_est >= 0:
                                row_count = int(fast_est)
                                is_exact = False
                                details["method"] = "pg_class.reltuples"
                            count_sql = f"SELECT COUNT(*) FROM {table_name}"
                        else:
                            count_sql = f"SELECT COUNT(*) FROM ({raw_query}) AS _subq"
                        
                        if not is_exact:
                            exact_count = await pg_conn.fetchval(count_sql)
                            if exact_count is not None:
                                row_count = int(exact_count)
                                is_exact = True
                                details["count_sql"] = count_sql

        except Exception as exc:
            logger.warning("[MigrationSizing] SQL count estimation query failed (%s). Using fallback: %s", exc, raw_query)
            row_count = 10_000
            is_exact = False
            details["error"] = str(exc)

        est_bytes = row_count * self.default_avg_row_bytes
        return SourceSizeEstimate(
            source_name=src.get("name", "sql_source"),
            source_type="database",
            row_count=row_count,
            estimated_bytes=est_bytes,
            estimated_mb=est_bytes / (1024 * 1024),
            is_exact=is_exact,
            details=details,
        )

    async def _estimate_nosql_source(
        self,
        src: Dict[str, Any],
        active_watermark: Optional[Any] = None,
    ) -> SourceSizeEstimate:
        row_count = 0
        is_exact = False
        details = {}

        try:
            adapter = create_nosql_connector(src)
            async with adapter:
                coll_name = src.get("collection", "default")
                query = dict(src.get("query") or {})
                delta_cfg = src.get("delta", {}) or {}
                wm_col = delta_cfg.get("watermark_column") or src.get("watermark_column")
                init_wm = delta_cfg.get("initial_watermark")
                effective_wm = active_watermark if active_watermark is not None else init_wm

                if wm_col and effective_wm is not None:
                    query[wm_col] = {"$gt": effective_wm}

                if hasattr(adapter, "_db") and adapter._db is not None:
                    coll = adapter._db[coll_name]
                    if not query:
                        row_count = await coll.estimated_document_count()
                        details["method"] = "estimated_document_count"
                    else:
                        row_count = await coll.count_documents(query)
                        details["method"] = "count_documents"
                    is_exact = True
        except Exception as exc:
            logger.warning("[MigrationSizing] NoSQL count estimation failed: %s", exc)
            row_count = 10_000
            is_exact = False
            details["error"] = str(exc)

        est_bytes = row_count * 800  # MongoDB documents typically slightly larger than flat SQL
        return SourceSizeEstimate(
            source_name=src.get("name", "mongo_source"),
            source_type="nosql",
            row_count=row_count,
            estimated_bytes=est_bytes,
            estimated_mb=est_bytes / (1024 * 1024),
            is_exact=is_exact,
            details=details,
        )

    async def _estimate_file_source(self, src: Dict[str, Any]) -> SourceSizeEstimate:
        path_str = src.get("path") or src.get("archive_path") or src.get("file_path")
        row_count = 0
        file_bytes = 0
        is_exact = False
        details = {}

        if path_str and os.path.exists(path_str):
            file_bytes = os.path.getsize(path_str)
            fmt = src.get("format", "csv").lower()
            if fmt == "csv":
                # Average CSV row ~ 150 bytes
                row_count = max(1, file_bytes // 150)
                details["calculated_from_csv_bytes"] = file_bytes
            elif fmt == "parquet":
                try:
                    import pyarrow.parquet as pq
                    meta = pq.read_metadata(path_str)
                    row_count = meta.num_rows
                    is_exact = True
                    details["parquet_num_rows"] = row_count
                except Exception:
                    row_count = max(1, file_bytes // 80)
            else:
                row_count = max(1, file_bytes // 200)
        else:
            row_count = 50_000
            file_bytes = row_count * self.default_avg_row_bytes

        return SourceSizeEstimate(
            source_name=src.get("name", "file_source"),
            source_type="file",
            row_count=row_count,
            estimated_bytes=file_bytes,
            estimated_mb=file_bytes / (1024 * 1024),
            is_exact=is_exact,
            details=details,
        )

    async def plan_migration_scaling(
        self,
        pipeline_config: Dict[str, Any],
        active_watermark: Optional[Any] = None,
    ) -> MigrationScalingPlan:
        pipeline_id = pipeline_config.get("pipeline_id", "unnamed_pipeline")
        tenant_id = pipeline_config.get("tenant_id", "default")
        settings = pipeline_config.get("settings", {}) or {}
        keda_cfg = settings.get("keda", {}) or {}

        keda_enabled = bool(keda_cfg.get("enabled", True))
        rows_per_worker = int(keda_cfg.get("rows_per_worker", self.default_rows_per_worker))
        min_replicas = int(keda_cfg.get("min_replicas", self.default_min_replicas))
        max_replicas = int(keda_cfg.get("max_replicas", self.default_max_replicas))

        sources = pipeline_config.get("sources", [])
        source_estimates: List[SourceSizeEstimate] = []
        total_rows = 0
        total_bytes = 0

        for src in sources:
            est = await self.estimate_source(src, active_watermark=active_watermark)
            source_estimates.append(est)
            total_rows += est.row_count
            total_bytes += est.estimated_bytes

        # Calculate optimal replica target:
        # Replicas = clamp(ceil(total_rows / rows_per_worker), min_replicas, max_replicas)
        if total_rows == 0:
            recommended_replicas = min_replicas
            recommended_shards = 1
        else:
            raw_replicas = math.ceil(total_rows / max(1, rows_per_worker))
            recommended_replicas = max(min_replicas, min(max_replicas, raw_replicas))
            
            # Recommended shards for parallel partitioning
            shard_size = max(100, min(50_000, rows_per_worker // 2 if rows_per_worker > 200 else rows_per_worker))
            recommended_shards = max(1, math.ceil(total_rows / shard_size))

        # Generate sample mathematical half-open shard intervals [Start_i, End_i)
        shard_intervals = []
        if total_rows > 0:
            rows_per_shard = math.ceil(total_rows / recommended_shards)
            for i in range(recommended_shards):
                s_idx = i * rows_per_shard
                e_idx = min(total_rows, (i + 1) * rows_per_shard)
                shard_intervals.append({
                    "shard_index": i,
                    "range_start": s_idx,
                    "range_end": e_idx,
                    "interval_notation": f"[{s_idx}, {e_idx})",
                    "estimated_rows": e_idx - s_idx,
                })

        plan = MigrationScalingPlan(
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            total_rows=total_rows,
            estimated_payload_mb=total_bytes / (1024 * 1024),
            recommended_replicas=recommended_replicas,
            recommended_shards=recommended_shards,
            rows_per_worker=rows_per_worker,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            keda_enabled=keda_enabled,
            sources=source_estimates,
            shard_intervals=shard_intervals,
        )

        logger.info(
            "[MigrationSizing] Plan computed for '%s': %d total rows (%.2f MB) -> %d recommended KEDA replicas (%d shards).",
            pipeline_id, total_rows, plan.estimated_payload_mb, recommended_replicas, recommended_shards,
        )
        return plan


class GlobalWorkloadRegistry:
    """
    Singleton registry tracking active migration workloads, pending rows,
    and KEDA replica demand for Prometheus scrapers and HPA controllers.
    """

    def __init__(self):
        self._active_plans: Dict[str, MigrationScalingPlan] = {}
        self._pending_rows_by_pipeline: Dict[str, int] = {}
        self._processed_rows_by_pipeline: Dict[str, int] = {}

    def register_workload(self, plan: MigrationScalingPlan) -> None:
        self._active_plans[plan.pipeline_id] = plan
        self._pending_rows_by_pipeline[plan.pipeline_id] = plan.total_rows
        self._processed_rows_by_pipeline[plan.pipeline_id] = 0

    def record_progress(self, pipeline_id: str, rows_processed: int) -> None:
        if pipeline_id in self._pending_rows_by_pipeline:
            cur_pending = self._pending_rows_by_pipeline[pipeline_id]
            new_pending = max(0, cur_pending - rows_processed)
            self._pending_rows_by_pipeline[pipeline_id] = new_pending
            self._processed_rows_by_pipeline[pipeline_id] = (
                self._processed_rows_by_pipeline.get(pipeline_id, 0) + rows_processed
            )

    def complete_workload(self, pipeline_id: str) -> None:
        self._pending_rows_by_pipeline[pipeline_id] = 0
        self._active_plans.pop(pipeline_id, None)

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        total_pending_rows = sum(self._pending_rows_by_pipeline.values())
        total_active_jobs = len(self._active_plans)
        
        # Max recommended replicas across active workloads, or 0 if idle
        if not self._active_plans:
            demand_replicas = 0
            total_shards = 0
        else:
            demand_replicas = sum(p.recommended_replicas for p in self._active_plans.values())
            total_shards = sum(p.recommended_shards for p in self._active_plans.values())

        return {
            "active_workloads": total_active_jobs,
            "total_pending_rows": total_pending_rows,
            "workload_demand_replicas": demand_replicas,
            "total_shards": total_shards,
            "pipelines": {
                pid: {
                    "pending_rows": self._pending_rows_by_pipeline.get(pid, 0),
                    "processed_rows": self._processed_rows_by_pipeline.get(pid, 0),
                    "recommended_replicas": plan.recommended_replicas,
                    "recommended_shards": plan.recommended_shards,
                }
                for pid, plan in self._active_plans.items()
            },
        }


# Global Singleton
global_workload_registry = GlobalWorkloadRegistry()
global_sizing_engine = MigrationSizingEngine()
