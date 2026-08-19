"""
veloctra_transformers/arrow_engine.py
======================================
Vectorised transformations over PyArrow RecordBatches using Polars LazyFrames + Custom Scripting.
"""

from __future__ import annotations

import gc
import json
import logging
from typing import Any, Callable, Dict, List, Optional

import polars as pl
import pyarrow as pa

logger = logging.getLogger(__name__)


class ArrowTransformEngine:
    def __init__(self, steps: Optional[List[Dict[str, Any]]] = None):
        self._steps = steps or []

    def process_batch(
        self,
        batch: pa.RecordBatch,
        custom_plugins: Optional[Dict[str, Callable[[pa.RecordBatch], pa.RecordBatch]]] = None,
    ) -> pa.RecordBatch:
        if batch.num_rows == 0:
            return batch

        lf = pl.from_arrow(batch).lazy()
        plugin_steps: List[Dict[str, Any]] = []
        script_steps: List[Dict[str, Any]] = []

        for step in self._steps:
            stype = step.get("type")
            if stype == "filter":
                expr_str = step["expression"]
                lf = lf.filter(pl.sql_expr(expr_str))
            elif stype == "cast" or stype == "type_cast":
                col = step["column"]
                target_type = getattr(pl, step.get("target_type", "Utf8").capitalize(), pl.Utf8)
                lf = lf.with_columns(pl.col(col).cast(target_type))
            elif stype in ("rename", "rename_field", "rename_column"):
                field_name = step.get("field") or step.get("column")
                new_name = step.get("new_name") or step.get("value") or step.get("target")
                mapping = step.get("mapping") or ({field_name: new_name} if field_name and new_name else {})
                if mapping:
                    lf = lf.rename(mapping)
            elif stype == "drop":
                cols = step["columns"]
                lf = lf.drop(cols)
            elif stype == "add_constant":
                col = step["column"]
                val = step["value"]
                lf = lf.with_columns(pl.lit(val).alias(col))
            elif stype == "script" or stype == "script_transform":
                script_steps.append(step)
            elif stype == "plugin":
                plugin_steps.append(step)
            else:
                logger.warning("[ArrowEngine] Unknown transformation type '%s' — skipping", stype)

        transformed_df = lf.collect()

        # Handle Custom Python/JS Expression Scripting for Objects & Arrays
        if script_steps:
            dict_rows = transformed_df.to_dicts()
            new_rows = []

            for row in dict_rows:
                row_copy = dict(row)
                for s in script_steps:
                    source_col = s.get("column")
                    target_col = s.get("target_column") or source_col or "script_result"
                    code_snippet = s.get("code") or s.get("expression") or ""

                    val = row_copy.get(source_col) if source_col else row_copy
                    
                    try:
                        # Environment for eval/exec: val (input value), row (full record), json, map_array_to_set helper
                        def map_array_to_set(arr, key_field="id"):
                            if isinstance(arr, str):
                                try:
                                    arr = json.loads(arr)
                                except Exception:
                                    return {}
                            if isinstance(arr, list):
                                return {str(item.get(key_field, idx)): item for idx, item in enumerate(arr) if isinstance(item, dict)}
                            return {}

                        env = {
                            "val": val,
                            "value": val,
                            "row": row_copy,
                            "json": json,
                            "map_array_to_set": map_array_to_set,
                        }
                        
                        # Evaluate Python expression
                        res = eval(code_snippet, {"__builtins__": None}, env)
                        if isinstance(res, (dict, list)):
                            res = json.dumps(res)
                        row_copy[target_col] = res
                    except Exception as err:
                        logger.warning("[ArrowEngine] Script eval failed for col '%s': %s", source_col, err)
                        row_copy[target_col] = str(val)

                new_rows.append(row_copy)

            transformed_df = pl.DataFrame(new_rows)

        out_table = transformed_df.to_arrow()
        combined_table = out_table.combine_chunks()
        batches = combined_table.to_batches()
        out_batch = batches[0] if batches else batch

        del lf
        del transformed_df
        del out_table
        del combined_table

        if custom_plugins and plugin_steps:
            for pstep in plugin_steps:
                pname = pstep["name"]
                if pname in custom_plugins:
                    out_batch = custom_plugins[pname](out_batch)

        return out_batch
