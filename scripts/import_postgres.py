"""
scripts/import_postgres.py
==========================
Streams and imports RawClaimBenef.csv directly from test_data/archive.zip into PostgreSQL
with real-time progress, timing metrics, and row count tracking using asyncpg.
"""

import asyncio
import os
import subprocess
import time
import asyncpg
import psutil

ZIP_PATH = "/Users/karthiksp/projects/etl-sql-nosql/test_data/archive.zip"
DB_NAME = "healthcare_claims"
DB_USER = os.environ.get("USER", "karthiksp")
TABLE_NAME = "raw_claim_benef"


async def run_import():
    print("=" * 70)
    print(" 🏥 Starting PostgreSQL High-Speed Ingestion: RawClaimBenef")
    print("=" * 70)

    start_time = time.time()
    proc = psutil.Process()

    print(f"Connecting to PostgreSQL database '{DB_NAME}' as user '{DB_USER}'...")
    conn = await asyncpg.connect(database=DB_NAME, user=DB_USER)

    # Truncate table before import
    await conn.execute(f"TRUNCATE TABLE {TABLE_NAME};")
    print(f"Table '{TABLE_NAME}' truncated.")

    cmd = f'unzip -p "{ZIP_PATH}" | psql -d "{DB_NAME}" -U "{DB_USER}" -c "\\copy {TABLE_NAME} FROM STDIN WITH (FORMAT csv, HEADER true, NULL \'\')"'
    
    print(f"Executing stream pipeline:\n{cmd}\n")
    ingest_start = time.time()
    
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    ingest_duration = time.time() - ingest_start

    if process.returncode != 0:
        print(f"❌ Ingestion failed with code {process.returncode}:\n{stderr}")
        await conn.close()
        return

    # Query loaded row count
    total_rows = await conn.fetchval(f"SELECT COUNT(*) FROM {TABLE_NAME};")
    table_size = await conn.fetchval(f"SELECT pg_size_pretty(pg_total_relation_size('{TABLE_NAME}'));")

    await conn.close()

    total_duration = time.time() - start_time
    throughput = total_rows / ingest_duration if ingest_duration > 0 else 0

    print("=" * 70)
    print(" ✅ Ingestion to PostgreSQL Completed Successfully!")
    print("=" * 70)
    print(f"📊 Total Rows Ingested : {total_rows:,}")
    print(f"💾 Table On-Disk Size  : {table_size}")
    print(f"⏱️ Ingest Time         : {ingest_duration:.2f} seconds ({ingest_duration/60:.2f} minutes)")
    print(f"⚡ Avg Ingest Rate     : {throughput:,.1f} rows/second")
    print(f"🧠 Peak Process RSS    : {proc.memory_info().rss / (1024*1024):.2f} MB")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_import())
