"""
apps/demos/demo_sql_to_parquet.py
==================================
Demo Application 1: High-Volume Relational Database to Partitioned Parquet Stream.

Demonstrates streaming from a relational database (SQLite/Postgres) into auto-partitioned
Parquet files with field-level AES-256-GCM encryption and FSM checkpointing.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM
from veloctra_state.state_store import StateStore



async def run_demo():
    print("==================================================================")
    print(" DEMO 1: High-Volume SQL -> Auto-Partitioned Parquet Lakehouse")
    print("==================================================================")

    db_path = Path("demo_sql_source.db")
    output_dir = Path("demo_parquet_output")

    # Step 1: Ensure sample dataset exists
    if not db_path.exists():
        print("Generating 10MB test database for demo...")
        from generate_synthetic_data import generate_data
        generate_data(db_path, target_size_mb=10.0)

    # Step 2: Define pipeline config
    config = {
        "project_id": "demo_parquet_workspace",
        "pipeline_id": "sql_to_parquet_stream",
        "name": "Relational to Parquet Lakehouse Migration",
        "mode": "bulk",
        "resilience": {
            "max_retries": 3,
            "initial_backoff_seconds": 1.0,
            "max_backoff_seconds": 10.0,
            "circuit_breaker_failure_threshold": 3,
            "circuit_breaker_cooldown_seconds": 5,
        },
        "memory_limits": {
            "max_batch_memory_mb": 256,
            "force_gc_every_n_chunks": 1,
        },
        "security": {
            "secrets_provider": "env",
            "field_encryption": {
                "enabled": True,
                "kms_key_id": "env:APP_ENCRYPTION_KEY",
            },
        },
        "source": {
            "type": "database",
            "driver": "sqlite",
            "connection_string": f"sqlite:///{db_path.absolute()}",
            "query": "SELECT tx_id, customer_id, customer_name, card_number, ssn, amount, status FROM transactions",
            "chunk_size": 5000,
        },
        "transformations": [
            {
                "type": "field_encrypt",
                "fields": ["card_number", "ssn"],
            },
            {
                "type": "add_constant",
                "column": "etl_ingested_by",
                "value": "Enterprise-ETL-Engine-v1",
            },
        ],
        "output_partitioning": {
            "format": "parquet",
            "file_prefix": "secured_transactions",
            "max_rows_per_file": 10_000,
            "max_file_size_mb": 5,
        },
        "destinations": [
            {
                "name": "lakehouse_parquet",
                "type": "object_store",
                "protocol": "file",
                "path": str(output_dir.absolute()),
            }
        ],
    }

    # Step 3: Run orchestrator
    store = StateStore("demo_state.db")
    await store.connect()
    fsm = PipelineFSM(state_store=store)

    job_id = f"job_parquet_{int(time.time())}"
    await fsm.create_job(job_id, tenant_id="demo_tenant")

    async def telemetry_logger(j_id: str, event: dict):
        if event.get("event") == "pipeline_progress":
            print(f"   [Telemetry] Rows: {event['rows_processed']:,} | Rate: {event['rows_per_sec']:,} r/s | RAM: {event['memory_percent']:.1f}%")

    orchestrator = PipelineOrchestrator(
        job_id=job_id,
        tenant_id="demo_tenant",
        config=config,
        fsm=fsm,
        store=store,
        broadcaster=telemetry_logger,
    )

    print(f"\n🚀 Launching orchestrator job '{job_id}'...")
    start_t = time.time()
    await orchestrator.run()
    elapsed = time.time() - start_t

    # Step 4: Verify output
    files = list(output_dir.glob("*.parquet")) if output_dir.exists() else []
    print(f"\n✅ Pipeline finished in {elapsed:.2f}s!")
    print(f"📦 Created {len(files)} partitioned Parquet files in '{output_dir}':")
    for f in files[:5]:
        size_kb = f.stat().st_size / 1024
        print(f"   - {f.name} ({size_kb:.1f} KB)")

    await store.close()


if __name__ == "__main__":
    # Ensure test key exists
    if "APP_ENCRYPTION_KEY" not in os.environ:
        import base64
        os.environ["APP_ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()

    asyncio.run(run_demo())
