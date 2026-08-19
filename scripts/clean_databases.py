#!/usr/bin/env python3
"""
scripts/clean_databases.py
===========================
Clean-slate database utility for Veloctra Data Platform.
Wipes and resets all development and runtime databases:
- MongoDB: Drops all collections in 'veloctra_system' and 'healthcare_dw'
- PostgreSQL: Cleans and truncates 'raw_claim_benef' in 'healthcare_claims'
- SQLite: Removes stale state files (*.db, *.db-wal, *.db-shm)
- File Output: Removes stale lakehouse output directories
"""

import asyncio
import os
import shutil
from pathlib import Path
import asyncpg
import motor.motor_asyncio

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
PG_URI = os.environ.get("PROD_SOURCE_DB_URI", "postgresql://karthiksp@localhost:5432/healthcare_claims")


async def clean_mongo():
    print("🍃 [MongoDB] Connecting to cluster at %s..." % MONGO_URI)
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    
    dbs_to_clean = ["veloctra_system", "healthcare_dw"]
    for db_name in dbs_to_clean:
        db = client[db_name]
        colls = await db.list_collection_names()
        print(f"   • Database '{db_name}' has collections: {colls}")
        for c in colls:
            await db[c].drop()
            print(f"     ↳ Dropped collection '{c}'")
        print(f"   ✓ Database '{db_name}' cleaned completely.")
    client.close()


async def clean_postgres():
    print("\n🐘 [PostgreSQL] Connecting to '%s'..." % PG_URI)
    try:
        conn = await asyncpg.connect(PG_URI)
        # Check if raw_claim_benef exists
        tbl_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'raw_claim_benef');"
        )
        if tbl_exists:
            await conn.execute("TRUNCATE TABLE raw_claim_benef;")
            print("   ✓ Table 'raw_claim_benef' truncated.")
        else:
            print("   • Table 'raw_claim_benef' does not exist yet (will be created on import).")
        await conn.close()
    except Exception as exc:
        print(f"   ⚠️ PostgreSQL notice: {exc}")


def clean_sqlite_and_files():
    print("\n📁 [Filesystem & SQLite] Removing stale state and output directories...")
    root = Path(".")
    
    # SQLite state files
    patterns = ["state.db*", "demo_state.db*", "benchmark_state.db*", "synthetic_benchmark.db*", "demo_dest*.db*"]
    for pat in patterns:
        for f in root.glob(pat):
            try:
                f.unlink()
                print(f"   ↳ Deleted SQLite file: {f.name}")
            except Exception as e:
                print(f"   ⚠️ Could not delete {f.name}: {e}")

    # Output folders
    out_dirs = ["output_claims_lakehouse", "demo_parquet_output", "benchmark_output"]
    for d_name in out_dirs:
        d = root / d_name
        if d.exists() and d.is_dir():
            shutil.rmtree(d)
            print(f"   ↳ Removed directory: {d_name}")

    print("   ✓ Filesystem state cleaned.")


async def main():
    print("=" * 70)
    print(" 🧹 Veloctra Data Platform — Database & Environment Reset")
    print("=" * 70)
    
    await clean_mongo()
    await clean_postgres()
    clean_sqlite_and_files()
    
    print("=" * 70)
    print(" ✅ All databases, collections, and state stores wiped for a fresh start!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
