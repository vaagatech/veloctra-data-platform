"""
tests/test_cli.py
=================
Tests for the Veloctra standalone CLI interface.
"""

import subprocess
import sys
import pytest


def test_cli_version():
    res = subprocess.run([sys.executable, "veloctra_cli.py", "version"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Veloctra Engine v1.0.0" in res.stdout


def test_cli_validate_success():
    res = subprocess.run(
        [sys.executable, "veloctra_cli.py", "validate", "--config", "configs/custom_script_pipeline.yaml"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "is valid" in res.stdout


def test_cli_validate_missing_file():
    res = subprocess.run(
        [sys.executable, "veloctra_cli.py", "validate", "--config", "non_existent_config.yaml"],
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "not found" in res.stderr
