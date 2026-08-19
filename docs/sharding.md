# ⚡ Process Sharding & Data Partitioning in Veloctra

Veloctra implements a **5-layer sharding and partitioning architecture** designed to maximize throughput while guaranteeing memory safety, zero data loss, and seamless horizontal scaling.

---

## 1. Mathematical Guarantees: Gapless & Overlap-Free Process Sharding

Distributed ETL pipelines must guarantee that shards process all data **without duplicate execution** and **without dropping records**. Veloctra enforces strict mathematical partitioning invariants:

### Zero-Overlap Invariant
Each shard $i$ is assigned a **half-open interval** $[Start_i, End_i)$ defined by:
```sql
WHERE id >= :start_id AND id < :end_id
```
Since $End_i = Start_{i+1}$, any boundary key $k = End_i$ is excluded from Shard $i$ and evaluated exclusively in Shard $i+1$, mathematically preventing duplicate processing.

### Zero-Drop Completeness
The total keyspace domain $\mathcal{D} = [\text{MinID}, \text{MaxID}]$ is divided such that:
$$\bigcup_{i=1}^{N} [Start_i, End_i) \equiv [\text{MinID}, \text{MaxID}]$$
Because the intervals are contiguous with zero internal gaps, every record in the table belongs to exactly one shard interval.

---

## 2. Delta Processing & High-Watermark CDC Synchronization

Veloctra includes native **Delta Processing** to capture only new or modified rows since the last successful sync:

1. **Watermark Discovery**: On startup, `PipelineOrchestrator` queries the `StateStore` for the latest committed `watermark_value` for the given `pipeline_id`.
2. **Dynamic Query Rewriting**: Injects the watermark filter into the source query:
   ```sql
   SELECT * FROM claims WHERE updated_at > '2026-01-03T10:00:00' ORDER BY updated_at ASC;
   ```
3. **In-Flight High-Watermark Calculation**: Computes $\text{HighWatermark} = \max(\text{batch}[\text{watermark\_col}])$ across PyArrow batches.
4. **Atomic Checkpoint Commit**: Stores the watermark with chunk offsets for crash-proof resumption.

```yaml
pipeline_id: pg_to_mongo_delta_claims
tenant_id: healthcare_enterprise

sources:
  - name: pg_claims_source
    type: database
    connection_string: "postgresql+asyncpg://user:secret@localhost:5432/claims_db"
    query: "SELECT id, beneficiary_id, amount, updated_at FROM raw_claims"
    chunk_size: 5000
    delta:
      enabled: true
      watermark_column: "updated_at"
      watermark_type: "timestamp"
      initial_watermark: "1970-01-01T00:00:00Z"

destinations:
  - name: mongo_claims_sink
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://localhost:27017"
    database: analytics_dw
    collection: claims
    upsert_key: "id"
```

---

## 3. Zero-Column CDC: Databases with No Timestamp or Watermark Columns

When database tables lack `updated_at` or sequence columns and undergo **in-place update queries or deletions**, Veloctra leverages the **Universal Checksum-Diff CDC Engine**:

1. **Row Checksum Hashing**: Computes a deterministic SHA-256 hash across non-key values: $\mathcal{H}(r) = \text{SHA256}(\text{JSON}(r_{\text{non-keys}}))$.
2. **Snapshot Diffing**: Compares the current snapshot against the state hash map:
   - **INSERT**: Key not present in previous state map.
   - **UPDATE**: Key exists with a modified row checksum (captures in-place updates).
   - **DELETE**: Key existed in previous state map but is absent in current table.
3. **Replication Streams**: For MongoDB, PostgreSQL, and MySQL, native Change Streams / WAL streaming with resume tokens capture real-time CDC transactions.

---

## 4. Idempotent Merge Strategies (Exactly-Once Semantics)

To prevent duplicate record accumulation during worker retries or stream restarts:

| Target Engine | Merge Strategy | Behavior Under Replay |
| :--- | :--- | :--- |
| **PostgreSQL** | `INSERT INTO ... ON CONFLICT (id) DO UPDATE SET ...` | Updated records overwrite old rows; duplicate insertions merged in-place. |
| **MongoDB** | `ReplaceOne(filter={"id": val}, replacement, upsert=True)` | Matching documents updated atomically in place; new keys inserted. |
| **SQLite** | `INSERT OR REPLACE INTO table (cols) VALUES (...)` | Existing primary key row replaced atomically. |
| **Parquet / S3** | Partition Overwrite (`part_{job_id}_{chunk_idx}.parquet`) | Checkpointed files replaced atomically on retry. |

---

## 4. In-Flight Adaptive Memory Sharding (`MemoryGuard`)

As batches enter the pipeline, `MemoryGuard` continuously monitors process RAM, OS CPU, and individual record sizes to dynamically adjust chunk boundaries:

- **Massive Records ($\ge$ 5 MB/row)**: Chunk size throttled to **1 record/chunk**.
- **Large Records ($\ge$ 100 KB/row)**: Chunk size throttled to **50 records/chunk**.
- **Resource Ceiling (> 75% RAM/CPU)**: Chunk size halved, micro-sleep backpressure applied, leaving $\ge 25\%$ headroom for GC.

---

## 5. Fault-Isolation Sub-Chunking (DLQ Routing)

When a vectorised PyArrow batch of 10,000 rows encounters corrupt or malformed rows:
1. The batch is automatically sub-sharded into single-row slices (`mini_batch = raw_batch.slice(i, 1)`).
2. The failing poison-pill record is captured with stack trace and isolated into the Dead Letter Queue (`dlq`).
3. All remaining valid records in the batch are recombined and loaded into the destination with zero data loss or job stoppage.

---

## 6. Destination File Sink Partitioning (`FilePartitioner`)

When exporting high-volume streams to data lakehouses (S3, GCS, or Local Filesystem):
- **Bounded Partitions**: High-throughput streams are automatically split across numbered partition files (`part_00001.parquet`, `part_00002.parquet`).
- **Trigger Conditions**: A new file is flushed whenever row count reaches `max_rows_per_file` (100,000 rows) or size reaches `max_file_size_mb` (100 MB).

