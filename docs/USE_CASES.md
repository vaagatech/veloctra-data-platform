# Veloctra Data Platform — Enterprise Use Cases & Architecture Guide

This document outlines key enterprise use cases, architectural patterns, resilience models, security specifications, and operational workflows enabled by the **Veloctra Data Platform**.

---

## 1. High-Volume Financial Transaction Stream with In-Flight AES-256 Encryption

### Problem Statement
Financial services require ingesting millions of credit card transactions and customer SSNs from high-throughput OLTP databases into enterprise lakehouses. Data protection regulations (PCI-DSS, GDPR, HIPAA) require sensitive fields to be encrypted **before** records touch disk or staging storage.

### Solution Pattern
1. **Source System:** PostgreSQL / SQLite transaction tables.
2. **Extraction Engine:** `SQLConnector` extracts records into zero-copy PyArrow record batches.
3. **In-Flight Encryption:** `CipherEngine` performs hardware-accelerated AES-256-GCM encryption on designated columns (`card_number`, `ssn`) in memory.
4. **Adaptive MemoryGuard:** Dynamically measures RAM usage. If RAM exceeds 85%, chunk sizes are automatically scaled down (from 10,000 to 2,500 records) to guarantee OOM prevention.
5. **Destination System:** Parquet Lakehouse or Target PostgreSQL with encrypted fields.

---

## 2. Real-Time REST API Ingestion & Webhook Event Streaming

### Problem Statement
Enterprise web applications and third-party SaaS vendors emit real-time event telemetry via REST HTTP endpoints. Data engineering teams need to capture, model, and land these event payloads into central reporting data stores with circuit breaker protection against API rate-limiting or outages.

### Solution Pattern
1. **Source System:** REST API Endpoints (`APIConnector`).
2. **Authentication:** Secret references resolved at runtime via environment variables or HashiCorp Vault (`env:APP_ENCRYPTION_KEY`).
3. **Circuit Breakers:** `CircuitBreaker` automaton (`CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF_OPEN`) trips if API endpoint fails 3 consecutive times, preventing cascading HTTP timeouts.
4. **Data Modeling:** Visual Data Modeler (`DataModelMapper`) maps JSON payload keys to relational column definitions.

---

## 3. NoSQL Document Store (MongoDB / Cassandra) to Delta Parquet Sync

### Problem Statement
Operational microservices store unstructured customer event streams in MongoDB collections. Business intelligence teams require structured, columnar query performance in Apache Parquet formats.

### Solution Pattern
1. **Source System:** MongoDB / Cassandra collections (`MongoConnector`).
2. **Vectorised Transformation:** Flattens nested BSON documents into columnar PyArrow batches.
3. **File Partitioning:** `FilePartitioner` partitions output files by date/region (`year=2026/month=08/day=12/chunk_0.parquet`).
4. **Dead Letter Queue (DLQ):** Unparseable or malformed documents are automatically isolated into DLQ tables with exact stack traces without stopping the pipeline.

---

## 4. Reusable Modular Configuration & Multi-Tenant Governance

### Problem Statement
Large enterprise organizations run hundreds of ETL pipelines across distinct department workspaces (`finance_prod_workspace`, `marketing_analytics_workspace`, `logistics_stream_workspace`). Manually writing duplicate connection strings, security rules, and retry policies introduces configuration drift and security risks.

### Solution Pattern
1. **Modular Sub-Configs:** Reusable specs like `sub_sql_creds_prod`, `sub_encryption_policy_std`, and `sub_resilience_high_avail` are defined once.
2. **Parent Inheritance:** Parent pipeline configs import sub-configs via `import_sub_configs: ["sub_encryption_policy_std"]`.
3. **Bulk Import:** Data platform engineers drag & drop or upload batch YAML/JSON specs using the Bulk Import utility.
4. **Enforced RBAC:** Role-based permissions matrix (`SuperAdmin`, `ProjectAdmin`, `Developer`, `Operator`, `Viewer`) controls project workspace isolation and secret visibility.

---

## 5. End-to-End Operational Observability & Audit Compliance

### Solution Pattern
1. **Real-Time WebSockets:** Live streaming telemetry updates throughput (rows/sec), memory pressure, and state progress directly to the Management Console UI.
2. **Audit Log:** SQLite WAL state store (`StateStore`) records immutable FSM state transition audit logs (`fsm_events`).
3. **One-Click DLQ Replay:** Operators review isolated failed records in the DLQ Inspector and trigger automatic replay once source system issues are resolved.
