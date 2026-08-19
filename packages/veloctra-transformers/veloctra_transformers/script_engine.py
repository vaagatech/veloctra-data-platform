"""
veloctra_transformers/script_engine.py
======================================
Custom Script Transformation Engine.
Executes custom Python / Pandas / Polars / PyArrow processing scripts
configured via UI (inline code) or imported via CI/CD (files / modules).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import pyarrow as pa

logger = logging.getLogger(__name__)


class ScriptExecutionError(Exception):
    """Raised when custom script execution fails or times out."""
    def __init__(self, message: str, error_trace: Optional[str] = None):
        super().__init__(message)
        self.error_trace = error_trace or message


class ScriptTransformEngine:
    """
    Sandboxed execution engine for user-defined transformation scripts.
    Supports inline scripts (UI) and external files/modules (CI/CD import).
    """

    def __init__(
        self,
        script_code: Optional[str] = None,
        script_path: Optional[Union[str, Path]] = None,
        module_name: Optional[str] = None,
        entrypoint: str = "transform",
        timeout_seconds: float = 30.0,
    ):
        self.script_code = script_code
        self.script_path = Path(script_path) if script_path else None
        self.module_name = module_name
        self.entrypoint = entrypoint
        self.timeout_seconds = timeout_seconds

        self._transform_fn: Optional[Callable] = None
        self._fn_flavor: str = "arrow"  # "arrow" | "pandas" | "polars" | "records"
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="veloctra_script_worker")
        self._compiled = False
        self._compile_or_load()

    def _compile_or_load(self) -> None:
        """Compiles inline code or loads the script module from disk."""
        if self.script_code:
            self._compile_inline()
        elif self.script_path:
            self._load_file()
        elif self.module_name:
            self._load_module()

    def _compile_inline(self) -> None:
        if not self.script_code:
            return
        exec_scope: Dict[str, Any] = {
            "pa": pa,
            "pyarrow": pa,
            "json": __import__("json"),
            "math": __import__("math"),
            "time": time,
        }
        try:
            import pyarrow.compute as pc
            exec_scope["pc"] = pc
        except ImportError:
            pass

        try:
            import pandas as pd
            exec_scope["pd"] = pd
            exec_scope["pandas"] = pd
        except ImportError:
            pass

        try:
            import polars as pl
            exec_scope["pl"] = pl
            exec_scope["polars"] = pl
        except ImportError:
            pass

        try:
            compiled = compile(self.script_code, "<inline_script>", "exec")
            exec(compiled, exec_scope, exec_scope)
        except Exception as exc:
            tb = traceback.format_exc()
            raise ScriptExecutionError(f"Compilation error in inline script: {exc}", error_trace=tb) from exc

        # Find entrypoint
        self._bind_entrypoint(exec_scope)

    def _load_file(self) -> None:
        if not self.script_path or not self.script_path.exists():
            raise ScriptExecutionError(f"Script file not found: '{self.script_path}'")

        try:
            mod_name = f"veloctra_script_{self.script_path.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, self.script_path)
            if spec is None or spec.loader is None:
                raise ScriptExecutionError(f"Could not load module spec for '{self.script_path}'")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            local_scope = mod.__dict__
            self._bind_entrypoint(local_scope)
        except Exception as exc:
            if isinstance(exc, ScriptExecutionError):
                raise
            tb = traceback.format_exc()
            raise ScriptExecutionError(f"Failed to load script '{self.script_path}': {exc}", error_trace=tb) from exc

    def _load_module(self) -> None:
        if not self.module_name:
            return
        try:
            mod = importlib.import_module(self.module_name)
            local_scope = mod.__dict__
            self._bind_entrypoint(local_scope)
        except Exception as exc:
            tb = traceback.format_exc()
            raise ScriptExecutionError(f"Failed to import module '{self.module_name}': {exc}", error_trace=tb) from exc

    def _bind_entrypoint(self, scope: Dict[str, Any]) -> None:
        if "transform_df" in scope and (self.entrypoint == "transform_df" or self.entrypoint not in scope):
            self._transform_fn = scope["transform_df"]
            self._fn_flavor = "pandas"
        elif "transform_polars" in scope and (self.entrypoint == "transform_polars" or self.entrypoint not in scope):
            self._transform_fn = scope["transform_polars"]
            self._fn_flavor = "polars"
        elif "transform_records" in scope and (self.entrypoint == "transform_records" or self.entrypoint not in scope):
            self._transform_fn = scope["transform_records"]
            self._fn_flavor = "records"
        elif self.entrypoint in scope and callable(scope[self.entrypoint]):
            self._transform_fn = scope[self.entrypoint]
            if "df" in self.entrypoint.lower() or "pandas" in self.entrypoint.lower():
                self._fn_flavor = "pandas"
            elif "polars" in self.entrypoint.lower():
                self._fn_flavor = "polars"
            elif "records" in self.entrypoint.lower():
                self._fn_flavor = "records"
            else:
                self._fn_flavor = "arrow"
        elif "transform" in scope and callable(scope["transform"]):
            self._transform_fn = scope["transform"]
            self._fn_flavor = "arrow"
        else:
            raise ScriptExecutionError(
                f"No valid transform function found in script. Expected 'def {self.entrypoint}(...)', "
                "'def transform(batch)', 'def transform_df(df)', 'def transform_polars(df)', or 'def transform_records(records)'."
            )
        self._compiled = True

    def process_batch_sync(self, batch: pa.RecordBatch) -> pa.RecordBatch:
        """Synchronously executes the transformation on a PyArrow RecordBatch."""
        if not self._compiled or self._transform_fn is None:
            return batch

        start_time = time.perf_counter()
        try:
            if self._fn_flavor == "arrow":
                result = self._transform_fn(batch)
                if isinstance(result, pa.Table):
                    return result.to_batches()[0] if result.num_rows > 0 else batch.slice(0, 0)
                if isinstance(result, pa.RecordBatch):
                    return result
                # Fallback check if user returned pandas DataFrame
                try:
                    import pandas as pd
                    if isinstance(result, pd.DataFrame):
                        return pa.RecordBatch.from_pandas(result)
                except ImportError:
                    pass
                raise ScriptExecutionError(f"Expected transform() to return RecordBatch or Table, got {type(result).__name__}")

            elif self._fn_flavor == "pandas":
                df = batch.to_pandas()
                res_df = self._transform_fn(df)
                return pa.RecordBatch.from_pandas(res_df)

            elif self._fn_flavor == "polars":
                import polars as pl
                pldf = pl.from_arrow(batch)
                res_pldf = self._transform_fn(pldf)
                arrow_table = res_pldf.to_arrow()
                return arrow_table.to_batches()[0] if arrow_table.num_rows > 0 else batch.slice(0, 0)

            elif self._fn_flavor == "records":
                records = batch.to_pylist()
                res_records = self._transform_fn(records)
                return pa.RecordBatch.from_pylist(res_records)

            return batch

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("[ScriptEngine] Execution error: %s\n%s", exc, tb)
            raise ScriptExecutionError(f"Script execution error: {exc}", error_trace=tb) from exc
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.debug("[ScriptEngine] Batch transformation executed in %.2f ms", elapsed_ms)

    async def process_batch(self, batch: pa.RecordBatch) -> pa.RecordBatch:
        """Asynchronously executes the transformation with timeout protection."""
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._thread_pool, self.process_batch_sync, batch),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ScriptExecutionError(f"Custom script execution timed out after {self.timeout_seconds}s") from exc
