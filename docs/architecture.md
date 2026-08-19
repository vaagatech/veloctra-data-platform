# Enterprise Production Architecture Blueprint

## Architectural Overview

The **Enterprise ETL Engine** is built as a zero-memory-leak, high-volume streaming data transformation and migration platform. It follows a decoupled monorepo design where storage connectors, resilience layers, state machines, and vectorised PyArrow transformers communicate via standard interfaces.

```
+-------------------------------------------------------------------------------------------------------------------+
|                                      REACT 18 + TYPESCRIPT MANAGEMENT CONSOLE                                     |
|  - RBAC Engine & Workspace Isolation                     - Interactive Config Editor & Schema Validator          |
|  - Real-Time WebSocket Progress Charts                   - FSM Job Monitor, DLQ Replay & Audit Logs               |
+-------------------------------------------------------------------------------------------------------------------+
                                                          | REST / WebSockets (JWT + TLS 1.3 + Secret Scrubbing)
                                                          v
+-------------------------------------------------------------------------------------------------------------------+
|                                      CONTROL PLANE & STATE MACHINE (etl-state)                                     |
|  - Deterministic 11-State FSM (CREATED -> VALIDATING -> EXTRACTING -> TRANSFORMING -> LOADING -> COMPLETED)        |
|  - SQLite WAL Checkpointing Engine (Atomic per-chunk progress saving & resume pointer restoration)               |
|  - Dead Letter Queue (DLQ) Inspector & Automated Row Replay Engine                                                |
+-------------------------------------------------------------------------------------------------------------------+
                                                          | Chunk Iteration & Flow Control
                                                          v
+-------------------------------------------------------------------------------------------------------------------+
|                                     DATA PLANE & STREAM PIPELINE (etl-orchestrator)                              |
|  - Adaptive MemoryGuard: Process RAM Monitoring & Dynamic Backpressure (Halves batch size > 85% RAM)               |
|  - Zero-Leak Deallocation: Explicit gc.collect() & PyArrow memory release on every chunk cycle                    |
+-------------------------------------------------------------------------------------------------------------------+
     |                                                    |                                                 |
     v                                                    v                                                 v
+------------------------+           +-----------------------------------------+         +--------------------------+
|  CONNECTORS            |           |  TRANSFORM ENGINE (etl-transformers)    |         |  RESILIENCE ENGINE       |
|  (etl-connectors)      |           |                                         |         |  (etl-resilience)        |
|  - SQL: Postgres, MySQL| --------> |  - Polars LazyFrames Vectorised Logic   | ------> |                          |
|    & SQLite (Cursor)   |           |  - AES-256-GCM Field-Level Encryption    |         |  - Circuit Breakers      |
|  - NoSQL: MongoDB,     |           |  - WeakRef Sandboxed Plugin Registry    |         |    (CLOSED/OPEN/HALF_OPEN)|
|    Cassandra, DynamoDB |           |  - Auto-Sized Partitioned File Sink     |         |  - AWS Full Jitter Retry |
|  - Object Store: S3,   |           |    (Parquet / CSV output files)        |         |    Exponential Backoff   |
|    GCS, Azure, Local   |           +-----------------------------------------+         +--------------------------+
+------------------------+
```

---

## Package Architecture (Monorepo)

The repository is partitioned into modular packages inside `packages/`:

| Package | Path | Description |
|---------|------|-------------|
| `etl-core` | [`packages/etl-core`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-core) | Protocols and base stream interfaces. |
| `etl-security` | [`packages/etl-security`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-security) | bcrypt hashing, JWT validation, 5-role RBAC, and Vault/AWS Secrets Manager resolution. |
| `etl-state` | [`packages/etl-state`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-state) | Deterministic 11-state FSM state machine and SQLite WAL checkpoint store. |
| `etl-resilience` | [`packages/etl-resilience`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-resilience) | Circuit Breaker automaton and AWS Full Jitter backoff logic. |
| `etl-connectors` | [`packages/etl-connectors`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-connectors) | Stream readers/writers for PostgreSQL, MySQL, SQLite, MongoDB, Cassandra, DynamoDB, and Object Storage. |
| `etl-transformers` | [`packages/etl-transformers`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-transformers) | Polars/PyArrow vectorised transformations, AES-256-GCM cipher engine, and plugin registry. |
| `etl-orchestrator` | [`packages/etl-orchestrator`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-orchestrator) | `PipelineOrchestrator` controller and `MemoryGuard` RAM backpressure manager. |
| `etl-api` | [`packages/etl-api`](file:///Users/karthiksp/projects/etl-sql-nosql/packages/etl-api) | FastAPI REST endpoints, security header middleware, and WebSocket telemetry broadcaster. |

---

## Finite State Machine (FSM) Transition Matrix

The state machine enforces valid execution flows. Invalid state skips raise `InvalidTransitionError`:

```
CREATED -> VALIDATING -> EXTRACTING -> TRANSFORMING -> LOADING -> CHECKPOINTING -> COMPLETED
                                |             |           |             |
                                v             v           v             | (Next Chunk)
                             PAUSED       RETRYING    DLQ_ROUTED <------+
                                |             |
                                +----> EXTRACTING (Resume)
```

---

## Resilience & Memory Management Guarantees

1. **AWS Full Jitter Backoff**:
   Calculated as `sleep = random.uniform(0, min(cap, base * 2^attempt))`. Prevents thundering-herd issues under database retries.
2. **Circuit Breaker Automaton**:
   State shifts `CLOSED` → `OPEN` (after 5 failures) → `HALF_OPEN` (after 30s cooldown). Prevents cascading failures into degraded backends.
3. **Adaptive MemoryGuard**:
   Monitors process RAM using `psutil`. If RAM exceeds 85%, chunk size is halved dynamically. If RAM exceeds 95%, execution pauses for GC.
