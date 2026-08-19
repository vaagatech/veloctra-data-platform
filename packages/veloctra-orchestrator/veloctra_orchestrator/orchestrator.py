"""
veloctra_orchestrator/orchestrator.py
======================================
Pipeline Orchestrator supporting Multi-Source extraction, Multi-Destination fan-out,
Intelligent MemoryGuard backpressure manager (75% limit & huge record adaptation),
and Per-Record Failure Isolation (DLQ routing without dropping valid items).
"""

from __future__ import annotations

import asyncio
import gc
import logging
import signal
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

import psutil
import pyarrow as pa

from veloctra_core.settings import get_settings
from veloctra_resilience.circuit_breaker import circuit_registry
from veloctra_security.rbac import assert_tenant_access
from veloctra_security.security import TokenPayload
from veloctra_state.fsm import FSMError, PipelineFSM, PipelineState
from veloctra_state.state_store import StateStore
from .extensions.rules_engine import RulesEngine
from .extensions.enrichment_engine import EnrichmentEngine
from veloctra_connectors.nosql_connector import create_nosql_connector
from veloctra_connectors.sql_connector import SQLConnector
from veloctra_connectors.universal_fs import UniversalFileSystem
from veloctra_transformers.arrow_engine import ArrowTransformEngine
from veloctra_transformers.cipher_engine import CipherEngine
from veloctra_transformers.file_partitioner import FilePartitioner
from veloctra_transformers.plugin_registry import PluginRegistry

logger = logging.getLogger(__name__)
settings = get_settings()


class MemoryGuard:
    """
    Intelligent Resource & Memory Guard.
    Enforces a strict 75% limit on RAM and CPU usage (reserving >= 25% for Garbage Collection).
    Dynamically resizes chunks based on individual record sizes (down to 1 row per chunk for huge payloads).
    """

    def __init__(
        self,
        max_ram_pct: float = 75.0,
        max_cpu_pct: float = 75.0,
        critical_ram_pct: float = 85.0,
        min_chunk: int = 1,
    ):
        self.max_ram_pct = max_ram_pct
        self.max_cpu_pct = max_cpu_pct
        self.critical_ram_pct = critical_ram_pct
        self.min_chunk = min_chunk

    def inspect_and_adapt(
        self,
        current_chunk_size: int,
        batch_bytes: Optional[int] = None,
        num_rows: Optional[int] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        mem_pct = psutil.virtual_memory().percent
        cpu_pct = psutil.cpu_percent()
        event_meta: Optional[Dict[str, Any]] = None

        # 1. Adaptive chunking based on huge record sizes
        if batch_bytes is not None and num_rows and num_rows > 0:
            avg_row_size = batch_bytes / num_rows
            
            # Massive multi-megabyte records (e.g. >= 5 MB per record) -> drop chunk to 1
            if avg_row_size >= 5 * 1024 * 1024:
                new_chunk = max(self.min_chunk, 1)
                logger.warning(
                    "[MemoryGuard] Massive records detected (avg %.2f MB/row). Reducing chunk size to %d.",
                    avg_row_size / (1024 * 1024), new_chunk,
                )
                event_meta = {
                    "guard_event": "huge_record_detected",
                    "avg_row_size_kb": round(avg_row_size / 1024, 2),
                    "old_chunk_size": current_chunk_size,
                    "new_chunk_size": new_chunk,
                }
                return new_chunk, event_meta

            # Huge records (avg >= 1 MB/row) -> drop chunk to max 5
            elif avg_row_size >= 1024 * 1024:
                new_chunk = min(current_chunk_size, max(self.min_chunk, 5))
                logger.warning(
                    "[MemoryGuard] Huge records detected (avg %.2f MB/row). Reducing chunk size to %d.",
                    avg_row_size / (1024 * 1024), new_chunk,
                )
                event_meta = {
                    "guard_event": "huge_record_detected",
                    "avg_row_size_kb": round(avg_row_size / 1024, 2),
                    "old_chunk_size": current_chunk_size,
                    "new_chunk_size": new_chunk,
                }
                return new_chunk, event_meta

            # Medium-large records (avg >= 100 KB/row) -> drop chunk to max 50
            elif avg_row_size >= 100 * 1024:
                new_chunk = min(current_chunk_size, max(self.min_chunk, 50))
                event_meta = {
                    "guard_event": "large_record_detected",
                    "avg_row_size_kb": round(avg_row_size / 1024, 2),
                    "old_chunk_size": current_chunk_size,
                    "new_chunk_size": new_chunk,
                }
                return new_chunk, event_meta

            # Single batch > 25MB -> halve chunk size aggressively
            if batch_bytes > 25 * 1024 * 1024:
                new_chunk = max(self.min_chunk, current_chunk_size // 2)
                logger.warning(
                    "[MemoryGuard] Batch payload is large (%.1f MB). Halving chunk size to %d.",
                    batch_bytes / (1024 * 1024), new_chunk,
                )
                event_meta = {
                    "guard_event": "batch_payload_large",
                    "batch_size_mb": round(batch_bytes / (1024 * 1024), 2),
                    "old_chunk_size": current_chunk_size,
                    "new_chunk_size": new_chunk,
                }
                return new_chunk, event_meta

        # 2. Critical usage (RAM or CPU > 85%) -> halving chunk size + GC
        if mem_pct > self.critical_ram_pct or cpu_pct > self.critical_ram_pct:
            logger.warning(
                "[MemoryGuard] Critical Resource Usage (RAM: %.1f%%, CPU: %.1f%% > 85%%). Halving chunk size & triggering GC…",
                mem_pct, cpu_pct,
            )
            gc.collect()
            time.sleep(0.3)
            new_chunk = max(self.min_chunk, current_chunk_size // 2)
            event_meta = {
                "guard_event": "critical_backpressure",
                "memory_percent": mem_pct,
                "cpu_percent": cpu_pct,
                "old_chunk_size": current_chunk_size,
                "new_chunk_size": new_chunk,
            }
            return new_chunk, event_meta

        # 3. Target threshold (RAM or CPU > 75%) -> throttle & reduce chunk size
        if mem_pct > self.max_ram_pct or cpu_pct > self.max_cpu_pct:
            logger.info(
                "[MemoryGuard] RAM/CPU usage above 75%% ceiling (RAM: %.1f%%, CPU: %.1f%%). Triggering GC & micro-sleep backpressure…",
                mem_pct, cpu_pct,
            )
            gc.collect()
            time.sleep(0.1)
            new_chunk = max(self.min_chunk, int(current_chunk_size * 0.75))
            event_meta = {
                "guard_event": "backpressure_applied",
                "memory_percent": mem_pct,
                "cpu_percent": cpu_pct,
                "old_chunk_size": current_chunk_size,
                "new_chunk_size": new_chunk,
            }
            return new_chunk, event_meta

        # 4. Recovery phase: if system is relatively idle (< 50%), recover chunk size smoothly
        if mem_pct < 50.0 and cpu_pct < 50.0 and current_chunk_size < settings.default_chunk_size:
            recovered_chunk = min(settings.default_chunk_size, int(current_chunk_size * 1.25) if current_chunk_size > 0 else 10)
            return recovered_chunk, None

        return current_chunk_size, None


class PipelineOrchestrator:
    def __init__(
        self,
        job_id: str,
        tenant_id: str,
        config: Dict[str, Any],
        fsm: PipelineFSM,
        store: StateStore,
        token: Optional[TokenPayload] = None,
        broadcaster: Optional[Callable] = None,
    ):
        if token:
            assert_tenant_access(token, config.get("project_id", tenant_id))

        self.job_id = job_id
        self.tenant_id = tenant_id
        self.config = config
        self.fsm = fsm
        self.store = store
        self.broadcaster = broadcaster

        self.memory_guard = MemoryGuard(
            max_ram_pct=settings.max_memory_percent,
            max_cpu_pct=getattr(settings, "max_cpu_percent", 75.0),
            critical_ram_pct=settings.critical_memory_percent,
            min_chunk=settings.min_chunk_size,
        )
        self._stop_requested = False
        self._plugin_registry = PluginRegistry()
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self.request_stop)
        except (NotImplementedError, RuntimeError):
            pass

    def request_stop(self) -> None:
        logger.warning("[Orchestrator:%s] Stop requested — draining pipeline cleanly…", self.job_id)
        self._stop_requested = True

    async def run(self) -> int:
        start_time = time.time()
        try:
            total_rows = await self._run_pipeline()
            return total_rows
        except Exception as exc:
            logger.error("[Orchestrator:%s] Pipeline execution failed: %s", self.job_id, exc, exc_info=True)
            try:
                await self.fsm.transition(self.job_id, PipelineState.FAILED, self.tenant_id, {"error": str(exc)})
            except FSMError:
                pass
            raise
        finally:
            elapsed = time.time() - start_time
            logger.info("[Orchestrator:%s] Pipeline run finished in %.2fs", self.job_id, elapsed)

    async def _run_pipeline(self) -> None:
        await self.fsm.transition(self.job_id, PipelineState.VALIDATING, self.tenant_id)

        # Support sources array or single source fallback
        raw_sources = self.config.get("sources")
        sources_list: List[Dict[str, Any]] = raw_sources if isinstance(raw_sources, list) else []
        if not sources_list and "source" in self.config and isinstance(self.config["source"], dict):
            sources_list = [self.config["source"]]

        default_chunk = settings.default_chunk_size
        chunk_size = sources_list[0].get("chunk_size", default_chunk) if sources_list else default_chunk

        start_chunk = await self.store.get_resume_chunk(self.job_id)

        await self.fsm.transition(self.job_id, PipelineState.EXTRACTING, self.tenant_id)

        cipher_engine: Optional[CipherEngine] = None
        sec_cfg = self.config.get("security", {})
        enc_cfg = sec_cfg.get("field_encryption", {})
        if enc_cfg.get("enabled") and enc_cfg.get("kms_key_id"):
            cipher_engine = CipherEngine(enc_cfg["kms_key_id"])

        transform_steps = self.config.get("transformations", [])
        transform_engine = ArrowTransformEngine(transform_steps)

        custom_plugins: Dict[str, Callable] = {}
        for step in transform_steps:
            if step.get("type") == "plugin":
                pname = step["name"]
                custom_plugins[pname] = self._plugin_registry.load_plugin(pname)

        # Extensions
        rules = self.config.get("rules", [])
        rules_engine = RulesEngine(rules)

        enrichments = self.config.get("enrichments", [])
        enrichment_engine = EnrichmentEngine(enrichments)

        dest_configs = self.config.get("destinations", [])
        partitioner: Optional[FilePartitioner] = None

        opt_part = self.config.get("output_partitioning")
        if opt_part:
            proto = dest_configs[0].get("protocol", "file") if dest_configs else "file"
            dest_path = dest_configs[0].get("path", "./output") if dest_configs else "./output"
            fs = UniversalFileSystem(protocol=proto, storage_options=dest_configs[0].get("storage_options"))
            partitioner = FilePartitioner(
                fs=fs,
                output_dir=dest_path,
                file_format=opt_part.get("format", "parquet"),
                file_prefix=opt_part.get("file_prefix", "part"),
                max_rows_per_file=opt_part.get("max_rows_per_file", 100_000),
                max_file_size_mb=opt_part.get("max_file_size_mb", 100.0),
            )

        chunk_idx = 0
        total_rows = 0

        extract_state = {"chunk_size": chunk_size}

        async for raw_batch in self._extract_multi_sources(sources_list, extract_state):
            if self._stop_requested:
                await self.fsm.transition(self.job_id, PipelineState.PAUSED, self.tenant_id)
                return

            if chunk_idx < start_chunk:
                chunk_idx += 1
                continue

            chunk_start = time.time()

            # ── Adaptive MemoryGuard Inspection ─────────────────────────────────
            chunk_size, guard_event = self.memory_guard.inspect_and_adapt(
                chunk_size,
                batch_bytes=raw_batch.nbytes,
                num_rows=raw_batch.num_rows,
            )
            extract_state["chunk_size"] = chunk_size

            if guard_event:
                await self._broadcast_telemetry({
                    "event": "memory_guard",
                    "job_id": self.job_id,
                    "tenant_id": self.tenant_id,
                    **guard_event,
                    "timestamp": time.time(),
                })

            await self.fsm.transition(self.job_id, PipelineState.TRANSFORMING, self.tenant_id, {"chunk_index": chunk_idx})

            # ── Transformations with Poison-Pill Isolation ───────────────────────
            batch = raw_batch
            try:
                # 1. Apply rules (filtering)
                batch = rules_engine.apply_rules(batch)
                if batch.num_rows > 0:
                    # 2. Data Enrichment
                    batch = await enrichment_engine.apply_enrichments(batch)

                    if cipher_engine and enc_cfg.get("fields_to_encrypt"):
                        batch = cipher_engine.encrypt_batch_fields(batch, enc_cfg["fields_to_encrypt"])

                    batch = transform_engine.process_batch(batch, custom_plugins)

                    if cipher_engine and enc_cfg.get("fields_to_decrypt"):
                        batch = cipher_engine.decrypt_batch_fields(batch, enc_cfg["fields_to_decrypt"])
            except Exception as transform_exc:
                logger.warning(
                    "[Orchestrator:%s] Vectorised transform failed for chunk %d: %s. Falling back to row-by-row transform...",
                    self.job_id, chunk_idx, transform_exc,
                )
                batch = await self._fallback_row_by_row_transform(
                    raw_batch, rules_engine, enrichment_engine, transform_engine, cipher_engine, enc_cfg, custom_plugins, chunk_idx
                )

            if batch.num_rows == 0:
                chunk_idx += 1
                del raw_batch
                del batch
                continue

            # ── Loading with Poison-Pill Isolation ───────────────────────────────
            await self.fsm.transition(self.job_id, PipelineState.LOADING, self.tenant_id, {"chunk_index": chunk_idx})

            loaded_rows = 0
            try:
                await self._load(batch, dest_configs, partitioner)
                loaded_rows = batch.num_rows
            except Exception as load_exc:
                logger.warning(
                    "[Orchestrator:%s] Batch loading failed for chunk %d: %s. Falling back to row-by-row load with DLQ isolation…",
                    self.job_id, chunk_idx, load_exc,
                )
                loaded_rows = await self._fallback_row_by_row_load(batch, dest_configs, partitioner, chunk_idx)

            if loaded_rows == 0:
                chunk_idx += 1
                del raw_batch
                del batch
                continue

            # ── Checkpointing ────────────────────────────────────────────────────
            await self.fsm.transition(self.job_id, PipelineState.CHECKPOINTING, self.tenant_id, {"chunk_index": chunk_idx})
            total_rows += loaded_rows

            await self.store.save_checkpoint(
                job_id=self.job_id,
                tenant_id=self.tenant_id,
                chunk_index=chunk_idx,
                state=PipelineState.COMPLETED.value,
                rows_written=total_rows,
            )

            chunk_elapsed = time.time() - chunk_start
            rate = int(loaded_rows / max(chunk_elapsed, 0.001))

            # ── Detailed Telemetry Broadcast ──────────────────────────────────────
            mem_info = psutil.virtual_memory()
            cpu_info = psutil.cpu_percent()

            await self._broadcast_telemetry({
                "event": "pipeline_progress",
                "job_id": self.job_id,
                "tenant_id": self.tenant_id,
                "rows_processed": total_rows,
                "chunks_processed": chunk_idx + 1,
                "rows_per_sec": rate,
                "memory_percent": mem_info.percent,
                "cpu_percent": cpu_info,
                "chunk_size": chunk_size,
                "chunk_latency_ms": round(chunk_elapsed * 1000, 2),
                "timestamp": time.time(),
            })

            # Clean memory dereferencing
            del raw_batch
            del batch

            # Periodic or pressure-driven garbage collection (avoiding latency in tight loops)
            if chunk_idx % 25 == 0 or mem_info.percent > 70.0:
                gc.collect()

            chunk_idx += 1

        if partitioner:
            partitioner.flush()

        await self.fsm.transition(self.job_id, PipelineState.COMPLETED, self.tenant_id, {"total_rows": total_rows})
        return total_rows

    async def _fallback_row_by_row_transform(
        self,
        raw_batch: pa.RecordBatch,
        rules_engine: Any,
        enrichment_engine: Any,
        transform_engine: Any,
        cipher_engine: Any,
        enc_cfg: Dict[str, Any],
        custom_plugins: Dict[str, Any],
        chunk_idx: int,
    ) -> pa.RecordBatch:
        """
        Slow path: Iterates row-by-row when vectorised batch processing encounters corrupt records.
        Safely isolates poison pill records, logs them to DLQ with error context, and returns all valid rows.
        """
        successful_batches = []
        for i in range(raw_batch.num_rows):
            mini_batch = raw_batch.slice(i, 1)
            try:
                batch = rules_engine.apply_rules(mini_batch)
                if batch.num_rows == 0:
                    continue

                batch = await enrichment_engine.apply_enrichments(batch)

                if cipher_engine and enc_cfg.get("fields_to_encrypt"):
                    batch = cipher_engine.encrypt_batch_fields(batch, enc_cfg["fields_to_encrypt"])

                batch = transform_engine.process_batch(batch, custom_plugins)

                if cipher_engine and enc_cfg.get("fields_to_decrypt"):
                    batch = cipher_engine.decrypt_batch_fields(batch, enc_cfg["fields_to_decrypt"])

                if batch.num_rows > 0:
                    successful_batches.append(batch)
            except Exception as e:
                logger.error(
                    "[Orchestrator:%s] Row %d in chunk %d failed transformation: %s. Isolating & routing to DLQ.",
                    self.job_id, i, chunk_idx, e,
                )
                try:
                    bad_row = mini_batch.to_pylist()[0]
                    dlq_id = await self.store.push_dlq(self.job_id, self.tenant_id, bad_row, str(e), chunk_idx)
                    await self._broadcast_telemetry({
                        "event": "record_failure",
                        "job_id": self.job_id,
                        "tenant_id": self.tenant_id,
                        "chunk_index": chunk_idx,
                        "row_index": i,
                        "error": str(e),
                        "dlq_id": dlq_id,
                        "timestamp": time.time(),
                    })
                except Exception as dlq_err:
                    logger.error("Failed to write to DLQ: %s", dlq_err)
                continue

        if not successful_batches:
            return raw_batch.slice(0, 0)

        return pa.Table.from_batches(successful_batches).combine_chunks().to_batches()[0]

    async def _fallback_row_by_row_load(
        self,
        batch: pa.RecordBatch,
        destinations: List[Dict[str, Any]],
        partitioner: Optional[FilePartitioner],
        chunk_idx: int,
    ) -> int:
        """
        Row-by-row fallback loader: Isolates single-row insert/upsert failures to DLQ
        and successfully writes all valid records.
        """
        successful_rows = 0
        for i in range(batch.num_rows):
            mini_batch = batch.slice(i, 1)
            row_dict = mini_batch.to_pylist()[0]
            try:
                await self._load(mini_batch, destinations, partitioner)
                successful_rows += 1
            except Exception as row_exc:
                logger.error(
                    "[Orchestrator:%s] Row %d in chunk %d failed load: %s. Isolating & routing to DLQ.",
                    self.job_id, i, chunk_idx, row_exc,
                )
                try:
                    dlq_id = await self.store.push_dlq(self.job_id, self.tenant_id, row_dict, str(row_exc), chunk_idx)
                    await self._broadcast_telemetry({
                        "event": "record_failure",
                        "job_id": self.job_id,
                        "tenant_id": self.tenant_id,
                        "chunk_index": chunk_idx,
                        "row_index": i,
                        "error": str(row_exc),
                        "dlq_id": dlq_id,
                        "timestamp": time.time(),
                    })
                except Exception as dlq_err:
                    logger.error("Failed to write failed record to DLQ: %s", dlq_err)

        if successful_rows < batch.num_rows:
            try:
                await self.fsm.transition(
                    self.job_id,
                    PipelineState.DLQ_ROUTED,
                    self.tenant_id,
                    {"chunk_index": chunk_idx, "failed_records": batch.num_rows - successful_rows},
                )
            except Exception:
                pass

        return successful_rows

    async def _extract_multi_sources(
        self,
        sources: List[Dict[str, Any]],
        state: Dict[str, int],
    ) -> AsyncGenerator[pa.RecordBatch, None]:
        """Extracts data from multiple source systems sequentially or concurrently."""
        for src in sources:
            stype = src.get("type", "database")

            if stype == "database":
                cb = circuit_registry.get_or_create(f"sql_extract_{src.get('name', 'db')}_{self.job_id}")
                async with cb:
                    async with SQLConnector(src["connection_string"]) as conn:
                        async for batch in conn.stream_read(src["query"], state["chunk_size"]):
                            yield batch

            elif stype == "nosql":
                adapter = create_nosql_connector(src)
                async with adapter:
                    async for batch in adapter.stream_read(src.get("collection", "default"), src.get("query"), chunk_size=state["chunk_size"]):
                        yield batch

            elif stype in ("file", "csv", "zip", "parquet"):
                from veloctra_connectors.file_connector import FileConnector
                cb = circuit_registry.get_or_create(f"file_extract_{src.get('name', 'file')}_{self.job_id}")
                async with cb:
                    async with FileConnector(src) as conn:
                        async for batch in conn.stream_read(state["chunk_size"]):
                            yield batch

            elif stype == "api":
                from veloctra_connectors.api_connector import APIConnector
                async with APIConnector(
                    endpoint_url=src.get("endpoint_url", "https://api.example.com/data"),
                    method=src.get("method", "GET"),
                    headers=src.get("headers"),
                    auth_token=src.get("auth_token"),
                    chunk_size=state["chunk_size"],
                ) as conn:
                    async for batch in conn.stream_read():
                        yield batch

            else:
                module_name = f"veloctra_connectors.{stype}_connector"
                class_name = f"{stype.title().replace('_', '')}Connector"
                try:
                    import importlib
                    module = importlib.import_module(module_name)
                    ConnectorClass = getattr(module, class_name)

                    async with ConnectorClass(src) as conn:
                        async for batch in conn.stream_read(state["chunk_size"]):
                            yield batch
                except ImportError:
                    logger.error("[Orchestrator] Plugin for source type '%s' not found (%s).", stype, module_name)
                except AttributeError:
                    logger.error("[Orchestrator] Plugin module '%s' does not contain class '%s'", module_name, class_name)
                except Exception as e:
                    logger.error("[Orchestrator] Error loading dynamic plugin '%s': %s", stype, e)

    async def _load(
        self,
        batch: pa.RecordBatch,
        destinations: List[Dict[str, Any]],
        partitioner: Optional[FilePartitioner] = None,
    ) -> None:
        if partitioner:
            partitioner.write_batch(batch)

        for dest in destinations:
            condition_expr = dest.get("condition")
            target_batch = batch

            if condition_expr:
                try:
                    import pyarrow.compute as pc
                    parts = condition_expr.split(" ")
                    if len(parts) >= 3:
                        field, op, val = parts[0], parts[1], parts[2].strip("'").strip('"')
                        col_data = target_batch[field]
                        if op == "==":
                            target_batch = target_batch.filter(pc.equal(col_data, val))  # type: ignore
                        elif op == "!=":
                            target_batch = target_batch.filter(pc.not_equal(col_data, val))  # type: ignore
                except Exception as e:
                    logger.error("[Orchestrator] Error evaluating condition '%s': %s", condition_expr, e)
                    continue

            if target_batch.num_rows == 0:
                continue

            dtype = dest["type"]
            cb = circuit_registry.get_or_create(f"load_{dest.get('name', 'dest')}_{self.job_id}")
            async with cb:
                if dtype == "database":
                    async with SQLConnector(dest["connection_string"]) as conn:
                        match_keys = dest.get("match_keys")
                        if match_keys:
                            await conn.bulk_upsert(dest["table"], target_batch, match_keys)
                        else:
                            await conn.bulk_insert(dest["table"], target_batch)

                elif dtype == "nosql":
                    adapter = create_nosql_connector(dest)
                    async with adapter:
                        records = target_batch.to_pylist()
                        await adapter.bulk_write(dest.get("collection", "processed_records"), records, dest.get("upsert_key"))

                elif dtype in ("file", "csv", "parquet", "storage"):
                    out_path_str = dest.get("output_dir") or dest.get("path") or "./output"
                    out_dir = Path(out_path_str)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    fmt = dest.get("format", "csv").lower()
                    if fmt == "parquet":
                        import pyarrow.parquet as pq
                        file_path = out_dir / f"{dest.get('name', 'export')}_{self.job_id}.parquet"
                        pq.write_table(pa.Table.from_batches([target_batch]), str(file_path))
                    else:
                        import pyarrow.csv as pa_csv
                        file_path = out_dir / f"{dest.get('name', 'export')}_{self.job_id}.csv"
                        table = pa.Table.from_batches([target_batch])
                        write_options = pa_csv.WriteOptions(include_header=not file_path.exists())
                        with open(file_path, "ab") as f:
                            pa_csv.write_csv(table, f, write_options=write_options)

    async def _broadcast_telemetry(self, event: Dict[str, Any]) -> None:
        if self.broadcaster:
            try:
                res = self.broadcaster(self.job_id, event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.warning("[Orchestrator:%s] Telemetry broadcast error: %s", self.job_id, exc)
