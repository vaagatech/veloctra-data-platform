"""
apps/demos/generate_synthetic_data.py
======================================
CLI tool to generate large synthetic financial datasets (10MB to 1GB+)
for high-volume ETL stream benchmarking and resilience testing.

Usage::

    # Generate a 10MB test database
    python3 apps/demos/generate_synthetic_data.py --size-mb 10 --output test_10mb.db

    # Generate a 100MB test database
    python3 apps/demos/generate_synthetic_data.py --size-mb 100 --output test_100mb.db

    # Generate a 1GB test database
    python3 apps/demos/generate_synthetic_data.py --size-mb 1000 --output test_1gb.db
"""

import argparse
import os
import random
import sqlite3
import time
import uuid
from pathlib import Path


FIRST_NAMES = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Skyler", "Dakota"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
STATUSES = ["COMPLETED", "PENDING", "FAILED", "FLAGGED", "SETTLED"]


def generate_ssn() -> str:
    return f"{random.randint(100, 999):03d}-{random.randint(10, 99):02d}-{random.randint(1000, 9999):04d}"


def generate_card() -> str:
    prefix = random.choice(["4111", "5500", "3700", "6011"])
    rest = "".join([str(random.randint(0, 9)) for _ in range(12)])
    return prefix + rest


def create_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            card_number TEXT NOT NULL,
            ssn TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def generate_data(output_path: Path, target_size_mb: float, batch_rows: int = 20_000):
    print(f"Generating synthetic dataset target size: {target_size_mb:.1f} MB at '{output_path}'...")
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(str(output_path))
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    create_schema(conn)

    start_time = time.time()
    total_rows = 0
    target_bytes = int(target_size_mb * 1024 * 1024)

    while True:
        rows = []
        for _ in range(batch_rows):
            tx_id = f"tx_{uuid.uuid4().hex[:16]}"
            cust_id = f"cust_{random.randint(10000, 99999)}"
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            card = generate_card()
            ssn = generate_ssn()
            amount = round(random.uniform(5.0, 5000.0), 2)
            status = random.choice(STATUSES)
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            rows.append((tx_id, cust_id, name, card, ssn, amount, status, now, now))

        conn.executemany("""
            INSERT INTO transactions
            (tx_id, customer_id, customer_name, card_number, ssn, amount, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

        total_rows += len(rows)
        current_bytes = output_path.stat().st_size
        elapsed = time.time() - start_time
        mb = current_bytes / (1024 * 1024)

        print(f"-> Generated {total_rows:,} rows ({mb:.2f} MB) in {elapsed:.1f}s ({total_rows/max(elapsed,0.1):,.0f} rows/s)")

        if current_bytes >= target_bytes:
            break

    conn.close()
    final_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Completed! Database created at '{output_path}' ({final_mb:.2f} MB, {total_rows:,} total rows).")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic dataset for high-volume ETL benchmarks.")
    parser.add_argument("--size-mb", type=float, default=20.0, help="Target database size in MB (e.g. 10, 100, 1000)")
    parser.add_argument("--output", type=str, default="synthetic_benchmark.db", help="Output SQLite file path")
    args = parser.parse_args()

    generate_data(Path(args.output), args.size_mb)


if __name__ == "__main__":
    main()
