"""
tests/test_memory_guard.py
===========================
Unit tests for the 75% MemoryGuard resource limits and adaptive huge-record chunking.
"""

import unittest.mock as mock
import pytest
from veloctra_orchestrator.orchestrator import MemoryGuard


def test_memory_guard_normal_conditions():
    guard = MemoryGuard(max_ram_pct=75.0, max_cpu_pct=75.0, critical_ram_pct=85.0, min_chunk=1)
    
    with mock.patch("psutil.virtual_memory") as mock_mem, mock.patch("psutil.cpu_percent") as mock_cpu:
        mock_mem.return_value.percent = 45.0
        mock_cpu.return_value = 40.0

        # Normal small records (1000 rows, 100KB total -> 100 bytes/row)
        chunk, event = guard.inspect_and_adapt(1000, batch_bytes=100 * 1024, num_rows=1000)
        # Should remain or recover smoothly
        assert chunk >= 1000
        assert event is None


def test_memory_guard_massive_records_adaptation():
    """Huge 6MB records should adaptively reduce chunk size to 1 (min_chunk)."""
    guard = MemoryGuard(max_ram_pct=75.0, max_cpu_pct=75.0, critical_ram_pct=85.0, min_chunk=1)
    
    with mock.patch("psutil.virtual_memory") as mock_mem, mock.patch("psutil.cpu_percent") as mock_cpu:
        mock_mem.return_value.percent = 55.0
        mock_cpu.return_value = 50.0

        # 10 rows taking 60MB -> 6MB / row
        chunk, event = guard.inspect_and_adapt(1000, batch_bytes=60 * 1024 * 1024, num_rows=10)
        assert chunk == 1
        assert event is not None
        assert event["guard_event"] == "huge_record_detected"
        assert event["new_chunk_size"] == 1


def test_memory_guard_large_records_adaptation():
    """1.5MB records should adaptively reduce chunk size to <= 5."""
    guard = MemoryGuard(max_ram_pct=75.0, max_cpu_pct=75.0, critical_ram_pct=85.0, min_chunk=1)
    
    with mock.patch("psutil.virtual_memory") as mock_mem, mock.patch("psutil.cpu_percent") as mock_cpu:
        mock_mem.return_value.percent = 55.0
        mock_cpu.return_value = 50.0

        # 10 rows taking 15MB -> 1.5MB / row
        chunk, event = guard.inspect_and_adapt(500, batch_bytes=15 * 1024 * 1024, num_rows=10)
        assert chunk <= 5
        assert event is not None
        assert event["guard_event"] == "huge_record_detected"


def test_memory_guard_75_percent_limit_backpressure():
    """When RAM exceeds 75%, MemoryGuard applies backpressure and throttles chunk size."""
    guard = MemoryGuard(max_ram_pct=75.0, max_cpu_pct=75.0, critical_ram_pct=85.0, min_chunk=1)
    
    with mock.patch("psutil.virtual_memory") as mock_mem, mock.patch("psutil.cpu_percent") as mock_cpu, mock.patch("time.sleep"):
        mock_mem.return_value.percent = 78.5
        mock_cpu.return_value = 50.0

        chunk, event = guard.inspect_and_adapt(1000, batch_bytes=1024, num_rows=10)
        assert chunk == 750 # Scaled down by 0.75
        assert event is not None
        assert event["guard_event"] == "backpressure_applied"
        assert event["memory_percent"] == 78.5


def test_memory_guard_critical_85_percent_limit():
    """When RAM or CPU exceeds 85%, MemoryGuard applies critical backpressure and halves chunk size."""
    guard = MemoryGuard(max_ram_pct=75.0, max_cpu_pct=75.0, critical_ram_pct=85.0, min_chunk=1)
    
    with mock.patch("psutil.virtual_memory") as mock_mem, mock.patch("psutil.cpu_percent") as mock_cpu, mock.patch("time.sleep"):
        mock_mem.return_value.percent = 88.0
        mock_cpu.return_value = 90.0

        chunk, event = guard.inspect_and_adapt(1000, batch_bytes=1024, num_rows=10)
        assert chunk == 500 # Halved
        assert event is not None
        assert event["guard_event"] == "critical_backpressure"
