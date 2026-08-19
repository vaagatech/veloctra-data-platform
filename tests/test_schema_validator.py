"""
tests/test_schema_validator.py
==============================
Unit tests for declarative DataQualityValidator assertions on PyArrow batches.
"""

import pytest
import pyarrow as pa
from veloctra_transformers.schema_validator import DataQualityValidator


def test_data_quality_not_null_and_range_assertions():
    contracts = {
        "not_null": ["id", "email"],
        "min_value": {"amount": 0},
        "max_value": {"age": 100},
        "allowed_values": {"status": ["ACTIVE", "PENDING"]},
        "regex_match": {"email": r"^[^@]+@[^@]+\.[^@]+$"},
    }

    validator = DataQualityValidator(contracts=contracts)

    batch = pa.RecordBatch.from_pydict({
        "id": [1, 2, 3, 4],
        "email": ["valid@test.com", "invalid-email", None, "ok@domain.org"],
        "amount": [150.0, -10.0, 50.0, 20.0],
        "age": [25, 40, 150, 30],
        "status": ["ACTIVE", "PENDING", "UNKNOWN", "ACTIVE"],
    })

    valid_batch, violations = validator.validate_batch(batch)

    # Rows 1 (index 0) and 4 (index 3) are completely valid
    assert valid_batch.num_rows == 2
    assert valid_batch.column(0).to_pylist() == [1, 4]

    # Rows 2 (index 1), 3 (index 2) had violations
    assert len(violations) == 2
    assert violations[0]["row_index"] == 1
    assert any("amount" in err for err in violations[0]["errors"])
    assert any("email" in err for err in violations[0]["errors"])


def test_data_quality_all_valid_pass_through():
    contracts = {
        "not_null": ["id"],
        "min_value": {"score": 10},
    }
    validator = DataQualityValidator(contracts=contracts)
    batch = pa.RecordBatch.from_pydict({
        "id": [101, 102],
        "score": [50, 95],
    })
    valid_batch, violations = validator.validate_batch(batch)
    assert valid_batch.num_rows == 2
    assert len(violations) == 0
