"""
scripts/migrate_postgres_to_mongo.py
====================================
End-to-End Migration Pipeline: PostgreSQL -> MongoDB
Executes high-throughput stream extraction, vectorised transformation,
MemoryGuard resource management, and bulk document insertion into MongoDB.
Tracks timing, throughput, batch statistics, and system metrics.
"""

import asyncio
import os
import time
from typing import Any, Dict
import psutil
import pymongo
import yaml

from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM
from veloctra_state.state_store import StateStore


CONFIG_PATH = "/Users/karthiksp/projects/etl-sql-nosql/configs/postgres_to_mongo_claims.yaml"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "healthcare_dw"
MONGO_COLL = "claim_beneficiaries"


async def run_migration(limit_rows: int = None):
    print("=" * 80)
    print(" 🚀 Veloctra Engine — PostgreSQL to MongoDB Migration Pipeline")
    print("=" * 80)

    # 1. Load configuration
    with open(CONFIG_PATH, "r") as f:
        config: Dict[str, Any] = yaml.safe_load(f)

    if limit_rows:
        # Modify query if row limit requested
        config["sources"][0]["query"] = f"SELECT * FROM raw_claim_benef LIMIT {limit_rows}"
        print(f"📌 Execution Mode: Sample of {limit_rows:,} rows")
    else:
        print("📌 Execution Mode: Full Dataset Stream")

    job_id = f"job_pg_to_mongo_{int(time.time())}"
    tenant_id = config.get("tenant_id", "healthcare_enterprise")

    # 2. Connect to State Store and FSM
    store = StateStore(adapter_type="sqlite", db_path="./state.db")
    await store.connect()
    fsm = PipelineFSM(state_store=store)
    await fsm.create_job(job_id, tenant_id)

    # 3. Telemetry callback for live progress logging
    telemetry_logs = []
    def on_telemetry(jid: str, event: Dict[str, Any]):
        evt_type = event.get("event")
        if evt_type == "pipeline_progress":
            rows = event.get("rows_processed", 0)
            rate = event.get("rows_per_sec", 0)
            ram = event.get("memory_percent", 0.0)
            chunk = event.get("chunk_size", 0)
            print(f"   [Telemetry] Processed: {rows:,} rows | Rate: {rate:,.0f} rows/s | RAM: {ram:.1f}% | Chunk: {chunk}")
            telemetry_logs.append(event)
        elif evt_type == "memory_guard":
            print(f"   [MemoryGuard] {event.get('guard_event')} -> chunk: {event.get('new_chunk_size')} (RAM: {event.get('memory_percent')}%, CPU: {event.get('cpu_percent')}%)")
        elif evt_type == "record_failure":
            print(f"   ⚠️ [DLQ Record Failure] Row in chunk {event.get('chunk_index')} isolated: {event.get('error')}")

    # 4. Initialize Orchestrator
    orchestrator = PipelineOrchestrator(
        job_id=job_id,
        tenant_id=tenant_id,
        config=config,
        fsm=fsm,
        store=store,
        broadcaster=on_telemetry,
    )

    print(f"\n⚡ Starting migration job '{job_id}'...")
    start_time = time.time()
    proc = psutil.Process()
    initial_rss = proc.memory_info().rss / (1024 * 1024)

    # 5. Run Orchestrator Pipeline
    total_rows = await orchestrator.run()
    elapsed = time.time() - start_time
    final_rss = proc.memory_info().rss / (1024 * 1024)
    avg_throughput = total_rows / elapsed if elapsed > 0 else 0

    # 6. Verify in MongoDB
    mongo_client = pymongo.MongoClient(MONGO_URI)
    mongo_db = mongo_client[MONGO_DB]
    mongo_coll = mongo_db[MONGO_COLL]
    
    doc_count = mongo_coll.count_documents({})
    coll_stats = mongo_db.command("collstats", MONGO_COLL)
    
    data_size_mb = coll_stats.get("size", 0) / (1024 * 1024)
    storage_size_mb = coll_stats.get("storageSize", 0) / (1024 * 1024)
    avg_obj_size = coll_stats.get("avgObjSize", 0)

    # Sample Document
    sample_doc = mongo_coll.find_one({}, {"_id": 0})

    print("\n" + "=" * 80)
    print(" ✅ Migration Summary & Metrics Report")
    print("=" * 80)
    print(f"⏱️ Total Elapsed Time       : {elapsed:.2f} seconds ({elapsed/60:.2f} mins)")
    print(f"📊 Total Rows Processed      : {total_rows:,}")
    print(f"⚡ Average Throughput        : {avg_throughput:,.1f} records / sec")
    print(f"🍃 MongoDB Total Documents   : {doc_count:,}")
    print(f"💾 MongoDB Data Size (MB)    : {data_size_mb:.2f} MB")
    print(f"📦 MongoDB Storage Size (MB) : {storage_size_mb:.2f} MB (WiredTiger compressed)")
    print(f"📏 Avg Document Size         : {avg_obj_size} bytes")
    print(f"🧠 Memory Usage              : Initial: {initial_rss:.1f} MB -> Final: {final_rss:.1f} MB (Peak Delta: {final_rss - initial_rss:+.1f} MB)")
    print(f"🛡️ Resource Limit Cap        : 75.0% RAM / 75.0% CPU")
    print("=" * 80)

    if sample_doc:
        print("\n🔍 Sample Ingested MongoDB Document (First 10 Fields):")
        for k in list(sample_doc.keys())[:10]:
            print(f"   - {k}: {sample_doc[k]}")
        print("   ...")

    await store.close()
    mongo_client.close()

    return {
        "job_id": job_id,
        "total_rows": total_rows,
        "elapsed_seconds": elapsed,
        "avg_throughput": avg_throughput,
        "mongo_doc_count": doc_count,
        "mongo_data_size_mb": data_size_mb,
        "sample_doc": sample_doc,
    }


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run_migration(limit_rows=limit))
