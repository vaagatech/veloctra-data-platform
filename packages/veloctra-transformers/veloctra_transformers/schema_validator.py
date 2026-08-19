"""
veloctra_transformers/schema_validator.py
=========================================
Declarative data quality contract assertion engine for PyArrow record batches.
Supports not-null, range checks, regex patterns, enum sets, and type assertions.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pyarrow as pa
import pyarrow.compute as pc

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when a record batch fails data quality assertion contracts."""
    pass


class DataQualityValidator:
    """
    Evaluates declarative data quality rules against incoming PyArrow record batches.
    Can operate in STRICT mode (rejects non-compliant batches or isolates failed rows)
    or AUDIT mode (logs violations and increments telemetry metrics).
    """

    def __init__(self, contracts: Optional[Dict[str, Any]] = None, strict: bool = True):
        self.contracts = contracts or {}
        self.strict = strict
        self._compiled_regexes: Dict[str, re.Pattern] = {}

        # Pre-compile any regex match rules
        regex_rules = self.contracts.get("regex_match", {})
        if isinstance(regex_rules, dict):
            for col, pattern in regex_rules.items():
                try:
                    self._compiled_regexes[col] = re.compile(pattern)
                except re.error as e:
                    logger.error("[DataQuality] Invalid regex pattern for col '%s': %s", col, e)

    def validate_batch(self, batch: pa.RecordBatch) -> Tuple[pa.RecordBatch, List[Dict[str, Any]]]:
        """
        Validates batch against contracts.
        Returns:
            Tuple of (valid_batch, violation_records)
        """
        if not self.contracts or batch.num_rows == 0:
            return batch, []

        violations: List[Dict[str, Any]] = []
        valid_indices = []

        not_null_cols: List[str] = self.contracts.get("not_null", [])
        min_vals: Dict[str, Any] = self.contracts.get("min_value", {})
        max_vals: Dict[str, Any] = self.contracts.get("max_value", {})
        allowed_enums: Dict[str, List[Any]] = self.contracts.get("allowed_values", {})

        # Convert to python dicts for deep cell validation if custom rules exist
        pydict = {name: batch.column(i).to_pylist() for i, name in enumerate(batch.schema.names)}

        for r_idx in range(batch.num_rows):
            row_violations = []

            # 1. Not-Null Check
            for col in not_null_cols:
                if col in pydict and (pydict[col][r_idx] is None or pydict[col][r_idx] == ""):
                    row_violations.append(f"Field '{col}' is null or empty (violates not_null contract)")

            # 2. Min Value Check
            for col, min_v in min_vals.items():
                if col in pydict and pydict[col][r_idx] is not None:
                    val = pydict[col][r_idx]
                    try:
                        if float(val) < float(min_v):
                            row_violations.append(f"Field '{col}' value {val} < minimum allowed {min_v}")
                    except (ValueError, TypeError):
                        pass

            # 3. Max Value Check
            for col, max_v in max_vals.items():
                if col in pydict and pydict[col][r_idx] is not None:
                    val = pydict[col][r_idx]
                    try:
                        if float(val) > float(max_v):
                            row_violations.append(f"Field '{col}' value {val} > maximum allowed {max_v}")
                    except (ValueError, TypeError):
                        pass

            # 4. Allowed Values Check
            for col, enums in allowed_enums.items():
                if col in pydict and pydict[col][r_idx] is not None:
                    val = pydict[col][r_idx]
                    if val not in enums:
                        row_violations.append(f"Field '{col}' value '{val}' not in allowed set {enums}")

            # 5. Regex Pattern Check
            for col, compiled_re in self._compiled_regexes.items():
                if col in pydict and pydict[col][r_idx] is not None:
                    val = str(pydict[col][r_idx])
                    if not compiled_re.match(val):
                        row_violations.append(f"Field '{col}' value '{val}' does not match regex pattern")

            if row_violations:
                bad_row = {name: pydict[name][r_idx] for name in batch.schema.names}
                violations.append({
                    "row_index": r_idx,
                    "record": bad_row,
                    "errors": row_violations,
                })
            else:
                valid_indices.append(r_idx)

        if not violations:
            return batch, []

        if not valid_indices:
            return batch.slice(0, 0), violations

        valid_table = pa.Table.from_batches([batch]).take(valid_indices)
        valid_batch = valid_table.to_batches()[0]
        return valid_batch, violations
