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
from veloctra_connectors.streaming_base import create_streaming_connector, BaseStreamingConnector
from veloctra_transformers.arrow_engine import ArrowTransformEngine
from veloctra_transformers.cipher_engine import CipherEngine
from veloctra_transformers.file_partitioner import FilePartitioner
from veloctra_transformers.plugin_registry import PluginRegistry
from veloctra_transformers.schema_validator import DataQualityValidator, SchemaValidationError
from veloctra_transformers.script_engine import ScriptTransformEngine, ScriptExecutionError

logger = logging.getLogger(__name__)
settings = get_settings()


class FailureThresholdExceeded(Exception):
    """Raised when pipeline failure rate exceeds configured threshold."""
    def __init__(self, message: str, stats: Dict[str, Any]):
        self.stats = stats
        super().__init__(message)


class FailurePolicy:
    """
    Configurable failure handling policy for pipeline execution.

    Policies:
      - 'continue':        Never stop for record-level failures. All bad records go to DLQ.
      - 'stop_on_failure':  Halt pipeline on the first record failure.
      - 'threshold':        Continue until failure rate exceeds configured thresholds, then halt.

    Thresholds are evaluated at two scopes:
      - Per-chunk:  Resets after each chunk. Catches concentrated bursts of bad data.
      - Per-run:    Cumulative across the entire pipeline execution.
    """

    def __init__(self, config: Dict[str, Any]):
        self.policy = config.get("policy", "continue").lower()
        self.log_level = config.get("log_level", "standard").lower()

        # Per-run (cumulative) thresholds
        self.max_failure_percent = float(config.get("max_failure_percent", 10.0))
        self.max_failure_count = int(config.get("max_failure_count", 0))  # 0 = unlimited

        # Per-chunk thresholds (optional — 0 means disabled)
        self.chunk_max_failure_percent = float(config.get("chunk_max_failure_percent", 0))
        self.chunk_max_failure_count = int(config.get("chunk_max_failure_count", 0))

        # Per-run counters
        self._total_processed: int = 0
        self._total_failed: int = 0

        # Per-chunk counters (reset each chunk)
        self._chunk_processed: int = 0
        self._chunk_failed: int = 0
        self._current_chunk_idx: int = -1

        self._halt_reason: Optional[str] = None

    def begin_chunk(self, chunk_idx: int) -> None:
        """Reset per-chunk counters at the start of a new chunk."""
        self._chunk_processed = 0
        self._chunk_failed = 0
        self._current_chunk_idx = chunk_idx

    def record_success(self, count: int = 1) -> None:
        """Record successfully processed rows."""
        self._total_processed += count
        self._chunk_processed += count

    def record_failure(self, count: int = 1) -> None:
        """Record failed rows and evaluate thresholds."""
        self._total_failed += count
        self._total_processed += count
        self._chunk_failed += count
        self._chunk_processed += count
        self._evaluate()

    def _evaluate(self) -> None:
        """Evaluate current state against the configured policy."""
        if self.policy == "continue":
            return

        if self.policy == "stop_on_failure":
            if self._total_failed > 0:
                self._halt_reason = (
                    f"Policy 'stop_on_failure': Pipeline halted after first record failure. "
                    f"Total failed: {self._total_failed}"
                )
            return

        if self.policy == "threshold":
            # ── Per-chunk absolute count ──────────────────────────────────────
            if self.chunk_max_failure_count > 0 and self._chunk_failed >= self.chunk_max_failure_count:
                self._halt_reason = (
                    f"Per-chunk failure count threshold breached in chunk {self._current_chunk_idx}: "
                    f"{self._chunk_failed} failures >= chunk_max_failure_count ({self.chunk_max_failure_count})"
                )
                return

            # ── Per-chunk percentage ──────────────────────────────────────────
            if self.chunk_max_failure_percent > 0 and self._chunk_processed > 0:
                chunk_pct = (self._chunk_failed / self._chunk_processed) * 100.0
                if chunk_pct >= self.chunk_max_failure_percent:
                    self._halt_reason = (
                        f"Per-chunk failure rate threshold breached in chunk {self._current_chunk_idx}: "
                        f"{chunk_pct:.2f}% >= chunk_max_failure_percent ({self.chunk_max_failure_percent}%). "
                        f"Failed: {self._chunk_failed}/{self._chunk_processed}"
                    )
                    return

            # ── Per-run absolute count ────────────────────────────────────────
            if self.max_failure_count > 0 and self._total_failed >= self.max_failure_count:
                self._halt_reason = (
                    f"Cumulative failure count threshold breached: {self._total_failed} failures "
                    f">= max_failure_count ({self.max_failure_count})"
                )
                return

            # ── Per-run percentage ────────────────────────────────────────────
            if self._total_processed > 0:
                pct = (self._total_failed / self._total_processed) * 100.0
                if pct >= self.max_failure_percent:
                    self._halt_reason = (
                        f"Cumulative failure rate threshold breached: {pct:.2f}% "
                        f">= max_failure_percent ({self.max_failure_percent}%). "
                        f"Failed: {self._total_failed}/{self._total_processed}"
                    )

    def should_halt(self) -> bool:
        """Returns True if the pipeline should stop based on current failure state."""
        return self._halt_reason is not None

    @property
    def halt_reason(self) -> Optional[str]:
        return self._halt_reason

    def get_summary(self) -> Dict[str, Any]:
        """Return a summary dict for telemetry / error payloads."""
        run_pct = (self._total_failed / self._total_processed * 100.0) if self._total_processed > 0 else 0.0
        chunk_pct = (self._chunk_failed / self._chunk_processed * 100.0) if self._chunk_processed > 0 else 0.0
        return {
            "policy": self.policy,
            "total_processed": self._total_processed,
            "total_failed": self._total_failed,
            "failure_rate_pct": round(run_pct, 2),
            "chunk_processed": self._chunk_processed,
            "chunk_failed": self._chunk_failed,
            "chunk_failure_rate_pct": round(chunk_pct, 2),
            "max_failure_percent": self.max_failure_percent,
            "max_failure_count": self.max_failure_count,
            "chunk_max_failure_percent": self.chunk_max_failure_percent,
            "chunk_max_failure_count": self.chunk_max_failure_count,
            "halted": self.should_halt(),
            "halt_reason": self._halt_reason,
        }


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
        self.pipeline_id = config.get("pipeline_id", job_id)
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
        except FailureThresholdExceeded as fte:
            import traceback
            tb = traceback.format_exc()
            logger.error("[Orchestrator:%s] Pipeline halted — failure threshold exceeded: %s", self.job_id, fte)
            try:
                await self.fsm.transition(self.job_id, PipelineState.FAILED, self.tenant_id, {
                    "error": str(fte),
                    "error_type": "FailureThresholdExceeded",
                    "traceback": tb,
                    "failure_policy": fte.stats,
                })
            except FSMError:
                pass
            await self.store.log_pipeline_event(
                self.job_id, self.tenant_id, "threshold_breached", "CRITICAL",
                message=str(fte), metadata=fte.stats,
            )
            raise
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            logger.error("[Orchestrator:%s] Pipeline execution failed: %s", self.job_id, exc, exc_info=True)
            try:
                await self.fsm.transition(self.job_id, PipelineState.FAILED, self.tenant_id, {
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "traceback": tb,
                })
            except FSMError:
                pass
            await self.store.log_pipeline_event(
                self.job_id, self.tenant_id, "pipeline_failed", "ERROR",
                message=str(exc), metadata={"error_type": exc.__class__.__name__, "traceback": tb},
            )
            raise
        finally:
            from veloctra_orchestrator.sizing_engine import global_workload_registry
            global_workload_registry.complete_workload(self.pipeline_id)
            elapsed = time.time() - start_time
            logger.info("[Orchestrator:%s] Pipeline run finished in %.2fs", self.job_id, elapsed)

    async def _run_pipeline(self) -> None:
        await self.fsm.transition(self.job_id, PipelineState.VALIDATING, self.tenant_id)

        # ── Failure Policy Configuration ─────────────────────────────────────
        eh_cfg = self.config.get("error_handling", {})
        failure_policy = FailurePolicy(eh_cfg)
        logger.info(
            "[Orchestrator:%s] Failure policy: %s (max_pct=%.1f%%, max_count=%d)",
            self.job_id, failure_policy.policy, failure_policy.max_failure_percent, failure_policy.max_failure_count,
        )
        await self.store.log_pipeline_event(
            self.job_id, self.tenant_id, "pipeline_start", "INFO",
            message=f"Pipeline started with failure policy '{failure_policy.policy}'",
            metadata={"failure_policy": failure_policy.get_summary(), "config_keys": list(self.config.keys())},
        )

        # Support sources array or single source fallback
        raw_sources = self.config.get("sources")
        sources_list: List[Dict[str, Any]] = raw_sources if isinstance(raw_sources, list) else []
        if not sources_list and "source" in self.config and isinstance(self.config["source"], dict):
            sources_list = [self.config["source"]]

        default_chunk = settings.default_chunk_size
        chunk_size = sources_list[0].get("chunk_size", default_chunk) if sources_list else default_chunk

        start_chunk = await self.store.get_resume_chunk(self.job_id)

        await self.fsm.transition(self.job_id, PipelineState.EXTRACTING, self.tenant_id)
        await self.store.log_pipeline_event(
            self.job_id, self.tenant_id, "extraction_start", "INFO",
            message=f"Starting extraction from {len(sources_list)} source(s)",
            metadata={"sources": [s.get('name', 'unknown') for s in sources_list]},
        )

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

        # Custom Script Transform Engine (UI inline code or CI/CD imported file/module)
        script_cfg = self.config.get("script") or self.config.get("custom_script") or self.config.get("script_transform")
        script_engine: Optional[ScriptTransformEngine] = None
        if script_cfg:
            if isinstance(script_cfg, str):
                script_engine = ScriptTransformEngine(script_code=script_cfg)
            elif isinstance(script_cfg, dict):
                script_engine = ScriptTransformEngine(
                    script_code=script_cfg.get("code") or script_cfg.get("script"),
                    script_path=script_cfg.get("path") or script_cfg.get("file"),
                    module_name=script_cfg.get("module"),
                    entrypoint=script_cfg.get("entrypoint", "transform"),
                    timeout_seconds=float(script_cfg.get("timeout_seconds", 30.0)),
                )

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
        current_high_watermark: Optional[str] = None

        dq_cfg = self.config.get("data_quality") or self.config.get("schema_contracts")
        validator = DataQualityValidator(contracts=dq_cfg, strict=dq_cfg.get("strict", False)) if dq_cfg else None

        extract_state = {"chunk_size": chunk_size}

        async for raw_batch in self._extract_multi_sources(sources_list, extract_state):
            if self._stop_requested:
                await self.fsm.transition(self.job_id, PipelineState.PAUSED, self.tenant_id)
                return

            if chunk_idx < start_chunk:
                chunk_idx += 1
                continue

            failure_policy.begin_chunk(chunk_idx)
            chunk_start = time.time()

            # ── Data Quality Contract Validation ────────────────────────────────
            if validator:
                valid_batch, violations = validator.validate_batch(raw_batch)
                if violations:
                    for v in violations:
                        await self.store.push_dlq(
                            self.job_id,
                            self.tenant_id,
                            v["record"],
                            f"DataQualityViolation: {', '.join(v['errors'])}",
                            chunk_idx,
                        )
                        failure_policy.record_failure()
                        await self.store.log_pipeline_event(
                            self.job_id, self.tenant_id, "data_quality_violation", "WARN",
                            chunk_index=chunk_idx,
                            message=f"DataQualityViolation: {', '.join(v['errors'])}",
                        )
                    if failure_policy.should_halt():
                        raise FailureThresholdExceeded(failure_policy.halt_reason, failure_policy.get_summary())
                    if dq_cfg.get("strict", False) and valid_batch.num_rows < raw_batch.num_rows:
                        raise SchemaValidationError(f"Batch {chunk_idx} failed strict data quality contracts ({len(violations)} violations)")
                raw_batch = valid_batch
                if raw_batch.num_rows == 0:
                    chunk_idx += 1
                    del raw_batch
                    continue

            # ── Track High-Watermark for Delta Sync ──────────────────────────────
            for src in sources_list:
                delta_cfg = src.get("delta", {}) or {}
                wm_col = delta_cfg.get("watermark_column") or src.get("watermark_column")
                if wm_col and wm_col in raw_batch.schema.names:
                    col_vals = raw_batch[wm_col].to_pylist()
                    valid_vals = [v for v in col_vals if v is not None]
                    if valid_vals:
                        batch_max = max(valid_vals)
                        batch_max_str = str(batch_max)
                        if current_high_watermark is None or batch_max_str > current_high_watermark:
                            current_high_watermark = batch_max_str

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

                    # 3. Custom Script Execution (Heavy UI / CI-CD processing)
                    if script_engine:
                        batch = await script_engine.process_batch(batch)

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
                await self.store.log_pipeline_event(
                    self.job_id, self.tenant_id, "transform_fallback", "WARN",
                    chunk_index=chunk_idx,
                    message=f"Vectorised transform failed: {transform_exc}",
                )
                batch = await self._fallback_row_by_row_transform(
                    raw_batch, rules_engine, enrichment_engine, transform_engine, cipher_engine, enc_cfg, custom_plugins, chunk_idx, script_engine,
                    failure_policy=failure_policy,
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
                await self.store.log_pipeline_event(
                    self.job_id, self.tenant_id, "load_fallback", "WARN",
                    chunk_index=chunk_idx,
                    message=f"Batch load failed: {load_exc}",
                )
                loaded_rows = await self._fallback_row_by_row_load(
                    batch, dest_configs, partitioner, chunk_idx,
                    failure_policy=failure_policy,
                )

            if loaded_rows == 0:
                chunk_idx += 1
                del raw_batch
                del batch
                continue

            # Track successful rows in failure policy
            failure_policy.record_success(loaded_rows)

            # ── Checkpointing ────────────────────────────────────────────────────
            await self.fsm.transition(self.job_id, PipelineState.CHECKPOINTING, self.tenant_id, {"chunk_index": chunk_idx})
            total_rows += loaded_rows

            await self.store.save_checkpoint(
                job_id=self.job_id,
                tenant_id=self.tenant_id,
                chunk_index=chunk_idx,
                state=PipelineState.COMPLETED.value,
                rows_written=total_rows,
                watermark_value=current_high_watermark,
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
                "watermark_value": current_high_watermark,
                "timestamp": time.time(),
            })

            await self.store.log_pipeline_event(
                self.job_id, self.tenant_id, "chunk_complete", "INFO" if failure_policy.log_level == "detailed" else "DEBUG",
                chunk_index=chunk_idx,
                message=f"Chunk {chunk_idx} completed: {loaded_rows} rows in {chunk_elapsed:.2f}s ({rate} rows/sec)",
                metadata={"loaded_rows": loaded_rows, "rate": rate, "chunk_elapsed_ms": round(chunk_elapsed * 1000, 2)},
            )

            from veloctra_orchestrator.sizing_engine import global_workload_registry
            global_workload_registry.record_progress(self.pipeline_id, loaded_rows)

            # Clean memory dereferencing
            del raw_batch
            del batch

            # Periodic or pressure-driven garbage collection (avoiding latency in tight loops)
            if chunk_idx % 25 == 0 or mem_info.percent > 70.0:
                gc.collect()

            chunk_idx += 1

        if partitioner:
            partitioner.flush()

        final_mem = psutil.virtual_memory()
        final_cpu = psutil.cpu_percent()
        proc = psutil.Process()
        proc_mem = round(proc.memory_info().rss / (1024 * 1024), 2)
        proc_cpu = proc.cpu_percent(interval=None)

        completion_metadata = {
            "total_rows": total_rows,
            "memory_percent": round(final_mem.percent, 1),
            "cpu_percent": final_cpu,
            "process_rss_mb": proc_mem,
            "process_cpu_percent": proc_cpu,
            **failure_policy.get_summary()
        }

        await self.fsm.transition(self.job_id, PipelineState.COMPLETED, self.tenant_id, completion_metadata)
        await self.store.log_pipeline_event(
            self.job_id, self.tenant_id, "pipeline_complete", "INFO",
            message=f"Pipeline completed successfully: {total_rows} total rows",
            metadata=completion_metadata,
        )
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
        script_engine: Optional[Any] = None,
        failure_policy: Optional[FailurePolicy] = None,
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

                if script_engine:
                    batch = await script_engine.process_batch(batch)

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
                    if failure_policy:
                        failure_policy.record_failure()
                    await self.store.log_pipeline_event(
                        self.job_id, self.tenant_id, "record_failure", "ERROR",
                        chunk_index=chunk_idx, row_index=i,
                        message=f"Transform failed: {e}",
                        metadata={"dlq_id": str(dlq_id), "error": str(e)},
                    )
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
                if failure_policy and failure_policy.should_halt():
                    raise FailureThresholdExceeded(failure_policy.halt_reason, failure_policy.get_summary())
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
        failure_policy: Optional[FailurePolicy] = None,
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
                    if failure_policy:
                        failure_policy.record_failure()
                    await self.store.log_pipeline_event(
                        self.job_id, self.tenant_id, "record_failure", "ERROR",
                        chunk_index=chunk_idx, row_index=i,
                        message=f"Load failed: {row_exc}",
                        metadata={"dlq_id": str(dlq_id), "error": str(row_exc)},
                    )
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
                if failure_policy and failure_policy.should_halt():
                    raise FailureThresholdExceeded(failure_policy.halt_reason, failure_policy.get_summary())

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
        """Extracts data from multiple source systems with automated Delta / Watermark injection."""
        pipeline_id = self.config.get("pipeline_id")
        last_committed_wm = await self.store.get_last_watermark(self.job_id, pipeline_id=pipeline_id)

        for src in sources:
            stype = src.get("type", "database")
            delta_cfg = src.get("delta", {}) or {}
            wm_col = delta_cfg.get("watermark_column") or src.get("watermark_column")
            wm_type = delta_cfg.get("watermark_type", "timestamp").lower()
            init_wm = delta_cfg.get("initial_watermark")
            active_wm = last_committed_wm if last_committed_wm is not None else init_wm

            if stype == "database":
                wm_clause: Optional[str] = None
                if wm_col and active_wm is not None:
                    if wm_type in ("int", "integer", "bigint", "float", "numeric", "number"):
                        wm_clause = f"{wm_col} > {active_wm}"
                    else:
                        safe_val = str(active_wm).replace("'", "''")
                        wm_clause = f"{wm_col} > '{safe_val}'"
                    logger.info(
                        "[Orchestrator:%s] Delta sync enabled for source '%s' (watermark: %s)",
                        self.job_id, src.get("name", "db"), active_wm,
                    )

                cb = circuit_registry.get_or_create(f"sql_extract_{src.get('name', 'db')}_{self.job_id}")
                async with cb:
                    async with SQLConnector(src["connection_string"]) as conn:
                        async for batch in conn.stream_read(src["query"], state["chunk_size"], watermark_clause=wm_clause):
                            yield batch

            elif stype == "nosql":
                adapter = create_nosql_connector(src)
                async with adapter:
                    if hasattr(adapter, "stream_read"):
                        async for batch in adapter.stream_read(
                            src.get("collection", "default"),
                            src.get("query"),
                            chunk_size=state["chunk_size"],
                            watermark_column=wm_col if active_wm is not None else None,
                            last_watermark=active_wm,
                        ):
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

            elif (
                stype in ("streaming", "kafka", "streaming_kafka", "rabbitmq", "amqp", "sqs", "aws_sqs", "redis", "redis_stream")
                or src.get("plugin_file")
                or src.get("plugin_module")
            ):
                cb = circuit_registry.get_or_create(f"stream_extract_{src.get('name', stype)}_{self.job_id}")
                async with cb:
                    conn = create_streaming_connector(src)
                    async with conn:
                        async for batch in conn.stream_read(state["chunk_size"]):
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

            # CDC Split: Deletes vs Upserts
            cdc_delete_batch = None
            cdc_upsert_batch = target_batch
            if "_cdc_op" in target_batch.schema.names:
                import pyarrow.compute as pc
                op_col = target_batch["_cdc_op"]
                del_mask = pc.equal(op_col, "DELETE")
                cdc_delete_batch = target_batch.filter(del_mask)
                cdc_upsert_batch = target_batch.filter(pc.invert(del_mask))

            dtype = dest["type"]
            cb = circuit_registry.get_or_create(f"load_{dest.get('name', 'dest')}_{self.job_id}")
            async with cb:
                if dtype == "database":
                    async with SQLConnector(dest["connection_string"]) as conn:
                        match_keys = dest.get("match_keys") or []
                        if cdc_delete_batch and cdc_delete_batch.num_rows > 0 and match_keys:
                            await conn.bulk_delete(dest["table"], cdc_delete_batch, match_keys)
                        if cdc_upsert_batch.num_rows > 0:
                            clean_cols = [c for c in cdc_upsert_batch.schema.names if not c.startswith("_cdc_")]
                            load_batch = cdc_upsert_batch.select(clean_cols) if clean_cols else cdc_upsert_batch
                            if match_keys:
                                await conn.bulk_upsert(dest["table"], load_batch, match_keys)
                            else:
                                await conn.bulk_insert(dest["table"], load_batch)

                elif dtype == "nosql":
                    adapter = create_nosql_connector(dest)
                    async with adapter:
                        records = cdc_upsert_batch.to_pylist() if cdc_upsert_batch.num_rows > 0 else []
                        if records:
                            await adapter.bulk_write(dest.get("collection", "processed_records"), records, dest.get("upsert_key"))

                elif (
                    dtype in ("streaming", "kafka", "streaming_kafka", "rabbitmq", "amqp", "sqs", "aws_sqs", "redis", "redis_stream")
                    or dest.get("plugin_file")
                    or dest.get("plugin_module")
                ):
                    conn = create_streaming_connector(dest)
                    async with conn:
                        clean_cols = [c for c in cdc_upsert_batch.schema.names if not c.startswith("_cdc_")]
                        load_batch = cdc_upsert_batch.select(clean_cols) if clean_cols else cdc_upsert_batch
                        await conn.publish_batch(load_batch, **dest)

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
