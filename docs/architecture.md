# 🏛️ Veloctra Production Architecture Blueprint

## Architectural Overview

The **Veloctra Data Platform** is built as an enterprise-grade, memory-governed streaming data transformation and migration platform. It follows a decoupled monorepo design where storage connectors, resilience layers, state machines, and vectorised PyArrow transformers communicate via standard protocols.

```mermaid
graph TD
    subgraph Client & Management Layer
        UI["🖥️ React 18 / Tailwind Management Console<br/>• Pipeline Studio (CRUD & 1-Click Publish)<br/>• Connection Manager (Encrypted Credentials)<br/>• Observability Center (Live Sparklines & Gauges)"]
    end

    subgraph Control Plane & Security
        API["⚡ FastAPI Enterprise Gateway (veloctra-api)<br/>• JWT Multi-Tenant Auth & 5-Role RBAC<br/>• Double Envelope Encryption Service (Fernet + ChaCha20)"]
        FSM["🔄 Finite State Machine (veloctra-state)<br/>• 11-State Deterministic Lifecycle<br/>• Dynamic MongoDB (veloctra_system) & SQLite Store"]
    end

    subgraph Data Plane & Execution Engine
        ORCH["⚙️ Pipeline Orchestrator (veloctra-orchestrator)<br/>• Intelligent MemoryGuard (75% RAM/CPU Ceiling)<br/>• Dynamic Chunk Sizing (10k → 50 → 1 row on huge blobs)<br/>• Fault-Isolated DLQ Row-by-Row Fallback Router"]
        TRANS["⚡ Vector Engine (veloctra-transformers)<br/>• PyArrow / Polars Columnar Transforms<br/>• Field-Level Column Encryption (AES-256-GCM)<br/>• Dynamic Rules & WeakRef Plugin Sandbox"]
    end

    subgraph Connectors & Sinks
        CONN["🔌 Universal Connectors (veloctra-connectors)<br/>• SQL: PostgreSQL (asyncpg), MySQL, SQLite<br/>• NoSQL: MongoDB, Cassandra, Redis, DynamoDB<br/>• Lakehouse: Parquet, CSV, S3, GCS, Local FilePartitioner"]
    end

    UI -->|REST & WebSockets| API
    API --> FSM
    API --> ORCH
    ORCH --> FSM
    ORCH --> TRANS
    ORCH --> CONN
```

---

## Package Architecture (Monorepo)

The repository is partitioned into 8 modular packages inside `packages/`:

| Package | Directory | Description |
| :--- | :--- | :--- |
| `veloctra-core` | `packages/veloctra-core` | Environment settings, Pydantic schema validation, and logging. |
| `veloctra-security` | `packages/veloctra-security` | Double Envelope Encryption (Fernet + ChaCha20-Poly1305), KeyRotationManager, 5-role RBAC, and Secret resolution. |
| `veloctra-state` | `packages/veloctra-state` | Deterministic 11-state FSM state machine and MongoDB (`veloctra_system`) / SQLite checkpoint store. |
| `veloctra-resilience` | `packages/veloctra-resilience` | Circuit Breaker automaton (CLOSED/OPEN/HALF_OPEN) and AWS Full Jitter exponential backoff. |
| `veloctra-connectors` | `packages/veloctra-connectors` | Streaming connectors for PostgreSQL, MySQL, SQLite, MongoDB, Cassandra, Redis, DynamoDB, and Universal File System. |
| `veloctra-transformers` | `packages/veloctra-transformers` | PyArrow / Polars columnar vector transformations, AES-256-GCM cipher engine, and auto-sized `FilePartitioner`. |
| `veloctra-orchestrator` | `packages/veloctra-orchestrator` | `PipelineOrchestrator` controller, `MemoryGuard` resource governor, and DLQ row-by-row fallback handler. |
| `veloctra-api` | `packages/veloctra-api` | FastAPI REST endpoints, security header middleware, and WebSocket telemetry broadcaster. |

---

## Finite State Machine (FSM) Transition Matrix

The state machine enforces valid execution flows. Invalid transitions raise `FSMError`:

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> VALIDATING
    VALIDATING --> EXTRACTING
    EXTRACTING --> TRANSFORMING
    TRANSFORMING --> LOADING
    LOADING --> CHECKPOINTING
    CHECKPOINTING --> TRANSFORMING: Next Batch
    CHECKPOINTING --> COMPLETED: Final Batch
    
    EXTRACTING --> PAUSED: User Action
    TRANSFORMING --> RETRYING: Network Glitch
    TRANSFORMING --> DLQ_ROUTED: Poison Pill Record
    LOADING --> DLQ_ROUTED: Insertion Error
    DLQ_ROUTED --> CHECKPOINTING: Valid Rows Saved
    
    PAUSED --> EXTRACTING: Resume
    RETRYING --> TRANSFORMING: Recovered
    COMPLETED --> [*]
```

---

## Double Envelope Encryption & Key Rotation

To protect database DSNs, API keys, and private tokens from filesystem leaks or database breaches, Veloctra enforces **Double Envelope Encryption**:

```
Plaintext Credential / Secret
             │
             ▼
[ Layer 1: Fernet (AES-128-CBC + HMAC-SHA256) with Master Key ]
             │
             ▼
[ Layer 2: ChaCha20-Poly1305 AEAD with Secondary Key + Tenant AAD ]
             │
             ▼
Stored Format: enc:v1:<nonce_b64>:<ciphertext_b64>
```

- **Zero Downtime Key Rotation**: When rotating keys (`v1` $\rightarrow$ `v2`), existing tokens remain decryptable while all new or updated credentials are automatically encrypted under the new active version.

---

## 🛡️ Field-Level Column Encryption (AES-256-GCM)

For HIPAA and GDPR compliance, sensitive PII/PHI columns (e.g. `ssn`, `beneficiary_id`, `credit_card`) are encrypted in-memory within PyArrow vector batches before writing to destinations:
- **Cipher**: AES-256-GCM with 96-bit unique nonces per record and 128-bit authentication tags.
- **Selective Column Policy**: Defined declaratively in pipeline configuration under `settings.encryption.fields_to_encrypt`.

---

## 👥 5-Role Multi-Tenant RBAC Authorization Matrix

| Role | Permissions | Scope |
| :--- | :--- | :--- |
| **SUPER_ADMIN** | Full system control, tenant creation, global key rotation, server metrics. | System-wide |
| **TENANT_ADMIN** | Manage pipelines, connection secrets, and team members within tenant. | Tenant-bound |
| **DATA_ENGINEER** | Create, edit, test, and publish pipeline definitions & transformations. | Tenant-bound |
| **OPERATOR** | Trigger pipeline executions, pause/resume jobs, view logs and DLQ items. | Tenant-bound |
| **AUDITOR** | Read-only access to audit trails, state checkpoints, and compliance logs. | Tenant-bound |

---

## ⚡ Universal Pluggable Streaming & Messaging Architecture

Veloctra features an open, pluggable streaming architecture (`BaseStreamingConnector` and `StreamingConnectorRegistry`):
- **Not Limited to Specific Vendors**: Any messaging/streaming system (**Apache Kafka**, **RabbitMQ**, **AWS SQS**, **Redis Streams**, **NATS**, **Google Cloud Pub/Sub**, **Azure Event Hubs**, **MQTT**, or proprietary message buses) can be integrated seamlessly.
- **Ultra-Lightweight Pod/Edge Footprint (< 40MB RAM)**: Base platform has zero mandatory broker dependencies; heavy client libraries load on-demand only when a connector is invoked.
- **Dynamic File / Module Loading**: Load custom connectors via `plugin_file: "plugins/custom_nats.py"` or `plugin_module: "my_org.connectors.solace"` with runtime hot-loading.
- **Bi-Directional Topologies**: Full support for Database $\leftrightarrow$ Messaging and Messaging $\leftrightarrow$ Messaging zero-broker bridging.

---

## 🐍 Custom Script Transformation Engine (UI & CI/CD Import)

For complex business processing and advanced data transformations beyond basic schema mappings:
- **UI Inline Scripting**: Author Python transformations directly within the UI designer, with live dry-run linting and validation via `POST /scripts/validate`.
- **CI/CD Module Import**: Import repository scripts or enterprise packages via `script_path` or `module_name`.
- **Multi-Framework Support**: Adapters for PyArrow (`pa.RecordBatch`), Pandas (`pd.DataFrame`), Polars (`pl.DataFrame`), and Python dictionary lists.
- **Execution Sandboxing**: Configurable timeout guards (`timeout_seconds`), memory thresholds, and per-record DLQ isolation.

---

## 🛡️ Intelligent MemoryGuard (75% Resource Ceiling)

The `MemoryGuard` protects the host system from out-of-memory crashes by maintaining strict resource governance:
1. **Dynamic Chunk Resizing**: Calculates record byte density per batch. For huge multi-megabyte payloads, chunk size is reduced to **1 record per chunk**.
2. **Resource Backpressure**: If RAM or CPU exceeds 75% or 85%, chunk sizes are halved and explicit Python Garbage Collection (`gc.collect()`) is triggered, reserving $\ge$25% headroom.

---

## 🔄 Universal Change Data Capture (CDC) Architecture

Veloctra combines **native in-app CDC engines** with **external log-based stream integrations**, delivering real-time synchronization, zero-data-loss replication, and legacy database delta extraction without requiring external agents like Debezium.

```mermaid
flowchart TD
    subgraph Sources ["1. Extraction & Change Detection"]
        A["🌊 High-Watermark Delta Sync<br/>(SQL & NoSQL Timestamp/Sequence)"] --> D["⚡ PyArrow Vector Stream"]
        B["🔍 ChecksumDiffCDC<br/>(Zero-Timestamp SHA-256 Hash Diff)"] --> D
        C["📜 MongoChangeStreamCDC<br/>(MongoDB Oplog + Resume Tokens)"] --> D
    end

    subgraph CDC_Format ["2. Unified CDC Metadata Contract"]
        D --> E["Injected Vector Columns:<br/>• _cdc_op: INSERT | UPDATE | DELETE<br/>• _cdc_ts: Epoch Timestamp<br/>• _cdc_key: Compound Primary Key"]
    end

    subgraph Sink ["3. Vector Split & Downstream Reconciliation"]
        E --> F{"_cdc_op == 'DELETE'?"}
        F -- "Yes (DELETE Batch)" --> G["🗑️ bulk_delete(match_keys)<br/>Target SQL DELETE WHERE key = ?"]
        F -- "No (Upsert Batch)" --> H["📥 bulk_upsert / bulk_write<br/>SQL ON CONFLICT DO UPDATE / Mongo ReplaceOne(upsert=True)"]
    end
```

### 1. Three CDC Operational Modes

| Mode | Engine Class / Layer | Target Use Case | Mechanism |
| :--- | :--- | :--- | :--- |
| **High-Watermark Delta Sync** | `PipelineOrchestrator` & `StateStore` | SQL & NoSQL tables with `updated_at`, `modified_ts`, or auto-incrementing `id` | Injects `WHERE watermark_col > 'last_wm'` at extract time. Continuously computes `max(batch[watermark_col])` and atomically stores it with chunk checkpoints. |
| **Snapshot Checksum Hash-Diff** | `ChecksumDiffCDC` (`cdc_engine.py`) | Legacy SQL / NoSQL tables with **no timestamps, no updated_at columns, and no replication stream access** | Computes deterministic SHA-256 hashes of non-key row attributes. Diffs incoming snapshots against cached state to emit `INSERT`, `UPDATE`, and `DELETE` events. |
| **Oplog Change Stream CDC** | `MongoChangeStreamCDC` (`cdc_engine.py`) | Real-time MongoDB collections & NoSQL oplogs | Subscribes to MongoDB change streams (`coll.watch()`) using `resume_after` tokens, transforming CRUD events into vectorized PyArrow batches. |

### 2. Checksum Hash-Diff CDC (`ChecksumDiffCDC`)

For databases where schema modification is forbidden or timestamp triggers are missing:
1. **Compound Key Resolution**: Combines primary key columns into a unique index key (`key_val = "101:US"`).
2. **Row-Level SHA-256 Hash**: Computes a deterministic hash across all non-key fields:
   $$\text{RowHash} = \text{SHA256}(\text{JSON}(\{k: v \mid k \notin \text{KeyColumns}\}))$$
3. **Change Detection Logic**:
   - **`INSERT`**: Key does not exist in the state map $\rightarrow$ Emit `_cdc_op = 'INSERT'`.
   - **`UPDATE`**: Key exists but $\text{RowHash}_{\text{new}} \neq \text{RowHash}_{\text{old}} \rightarrow$ Emit `_cdc_op = 'UPDATE'`.
   - **`DELETE`**: Key in previous state map missing from snapshot $\rightarrow$ Emit `_cdc_op = 'DELETE'` with cached key values.

### 3. PyArrow Vector Batch Splitting & Downstream Reconciliation

In the load phase (`PipelineOrchestrator._load`), incoming record batches containing `_cdc_op` metadata are split using zero-copy SIMD filters:

```python
# PyArrow Vectorized CDC Split
op_col = target_batch["_cdc_op"]
del_mask = pc.equal(op_col, "DELETE")
cdc_delete_batch = target_batch.filter(del_mask)
cdc_upsert_batch = target_batch.filter(pc.invert(del_mask))
```

- **Deletions (`cdc_delete_batch`)**: Dispatched to `SQLConnector.bulk_delete()` to execute parameterized `DELETE FROM table WHERE key1 = ? AND key2 = ?`.
- **Upserts (`cdc_upsert_batch`)**: Internal `_cdc_*` metadata columns are stripped, and batches are passed to `bulk_upsert()` (`ON CONFLICT (match_keys) DO UPDATE SET ...`) or MongoDB `ReplaceOne(filter, record, upsert=True)`.

### 4. Offset Governance & Replay Policies (UI & API)

When updating active CDC pipeline configurations, the platform provides atomic offset conflict resolution via the API (`POST /pipelines/config`) and UI (`ConfigEditor.tsx`):
- **`replay_from_start`**: Resets all stored high-watermarks and state hashes to `0` / empty, triggering a complete initial backfill before re-attaching the CDC delta stream.
- **`process_new_only`**: Preserves existing high-watermarks and state checkpoints, seamlessly capturing only newly created or modified events going forward.

### 5. Sample CDC Pipeline Configuration (YAML)

```yaml
pipeline_id: postgres_to_mongo_cdc
tenant_id: healthcare_prod_workspace
version: 2

sources:
  - name: pg_claims_cdc
    type: database
    connection_string: "enc:v1:..."
    query: "SELECT * FROM raw_claims"
    chunk_size: 5000
    delta:
      watermark_column: updated_at
      watermark_type: timestamp
      initial_watermark: "2026-01-01T00:00:00"

destinations:
  - name: mongo_claims_sink
    type: nosql
    db_type: mongodb
    connection_string: "enc:v1:..."
    database: analytics_dw
    collection: claims
    upsert_key: claim_id
```


