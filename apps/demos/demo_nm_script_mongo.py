"""
demo_nm_script_mongo.py
========================
End-to-End Demonstration:
1. Pluggable MongoDB State Store Adapter (local MongoDB on localhost:27017).
2. N:M Multi-Source -> Multi-Destination Pipeline execution.
3. Custom Python Expression Scripting (converting array of objects to map/set).
"""

import asyncio
import json
import os
import sqlite3
import time
import motor.motor_asyncio

from veloctra_orchestrator.orchestrator import PipelineOrchestrator
from veloctra_state.fsm import PipelineFSM
from veloctra_state.state_store import StateStore


def create_demo_data():
    # 1. Setup SQLite Source
    conn = sqlite3.connect("demo_source_nm.db")
    conn.execute("DROP TABLE IF EXISTS orders")
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_name TEXT,
            items_json TEXT,
            updated_at TEXT
        )
    """)
    items_sample = [
        {"item_id": "SKU-001", "product": "Pro Mechanical Keyboard", "qty": 2, "price": 149.99},
        {"item_id": "SKU-002", "product": "4K Ultra Monitor", "qty": 1, "price": 499.99},
    ]
    conn.execute(
        "INSERT INTO orders VALUES (1, 'Alice Smith', ?, '2026-08-12 08:00:00')",
        (json.dumps(items_sample),)
    )
    conn.commit()
    conn.close()

    # 2. Setup SQLite Target Destination
    conn_dest = sqlite3.connect("demo_dest_nm.db")
    conn_dest.execute("DROP TABLE IF EXISTS processed_orders")
    conn_dest.execute("""
        CREATE TABLE processed_orders (
            id INTEGER PRIMARY KEY,
            customer_name TEXT,
            items_json TEXT,
            updated_at TEXT,
            platform_version TEXT,
            items_map_set TEXT
        )
    """)
    conn_dest.commit()
    conn_dest.close()



async def run_demo():
    print("\n==================================================================")
    print(" 🚀 Veloctra Data Platform — N:M Multi-Source & Mongo State Store Demo")
    print("==================================================================\n")

    create_demo_data()

    # Configure Pluggable State Store to use local MongoDB
    mongo_uri = os.environ.get("VELOCTRA_MONGO_URI", "mongodb://localhost:27017")
    print(f"📦 Initializing Pluggable State Store adapter using MongoDB at '{mongo_uri}'...")
    
    store = StateStore(adapter_type="mongo", mongo_uri=mongo_uri)
    await store.connect()

    fsm = PipelineFSM(state_store=store)


    pipeline_config = {
        "project_id": "finance_prod_workspace",
        "pipeline_id": "nm_multi_source_demo",
        "mode": "hybrid",
        "sources": [
            {
                "name": "sql_orders_db",
                "type": "database",
                "connection_string": "sqlite:///demo_source_nm.db",
                "query": "SELECT * FROM orders",
                "chunk_size": 1000,
            }
        ],
        "transformations": [
            {
                "type": "add_constant",
                "column": "platform_version",
                "value": "v1.0-enterprise",
            },
            {
                "type": "script_transform",
                "column": "items_json",
                "target_column": "items_map_set",
                "code": "map_array_to_set(val, 'item_id')",
            }
        ],
        "destinations": [
            {
                "name": "sql_dest_replica",
                "type": "database",
                "connection_string": "sqlite:///demo_dest_nm.db",
                "table": "processed_orders",
                "match_keys": ["id"],
            }
        ]
    }

    job_id = "job_nm_demo_01"
    tenant_id = "finance_prod_workspace"

    await fsm.create_job(job_id, tenant_id)

    orchestrator = PipelineOrchestrator(
        job_id=job_id,
        tenant_id=tenant_id,
        config=pipeline_config,
        fsm=fsm,
        store=store,
    )

    print("⚡ Executing Multi-Source Extraction & Field Scripting Transformation...")
    await orchestrator.run()

    # Verify State Store in MongoDB
    print("\n🔍 Verifying state checkpoints and audit trail in local MongoDB...")
    cp = await store.get_latest_checkpoint(job_id)
    print(f"✅ Checkpoint in MongoDB: {cp}")

    events = await store.get_audit_events(job_id, limit=5)
    print(f"✅ Audit Log Entries in MongoDB: {len(events)} events recorded.")

    # Verify Processed Output in Destination Database
    conn = sqlite3.connect("demo_dest_nm.db")
    cur = conn.cursor()
    cur.execute("SELECT id, customer_name, platform_version, items_map_set FROM processed_orders")
    rows = cur.fetchall()
    print("\n🎯 Destination Database Verification:")
    for r in rows:
        print(f"  Row -> ID: {r[0]} | Customer: {r[1]} | Platform: {r[2]}")
        print(f"  Mapped Object Set (Array -> Map Conversion): {r[3]}")
    conn.close()

    await store.close()
    print("\n==================================================================")
    print(" ✅ Live N:M Multi-Source & MongoDB State Store Demo Successful!")
    print("==================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
