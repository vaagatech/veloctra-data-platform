# 🧪 Pipeline Configuration Examples

Explore practical pipeline declarations for common enterprise integration and migration patterns.

---

## 1. High-Volume CSV Zip Stream to PostgreSQL

Streams compressed CSV rows directly from zip files into PostgreSQL using `asyncpg.copy_records_to_table`:

```yaml
id: csv_to_postgres
name: "Medicare Claims Bulk Ingestion"
tenant_id: "healthcare_prod"

state_store:
  backend: mongodb
  database: veloctra_system

sources:
  - name: zip_claims_stream
    type: file
    format: csv
    archive_format: zip
    path: "./test_data/RawClaimBenef.csv.zip"
    chunk_size: 10000

transformers:
  rules:
    - field: "clm_id"
      rule: "not_null"
  enrichments:
    - type: "timestamp_utc"
      target_field: "ingested_at"

destinations:
  - name: postgres_lakehouse
    type: database
    connection_string: "postgresql+asyncpg://karthiksp@localhost:5432/healthcare_claims"
    table: "raw_claim_benef"
    upsert_key: "id"
```

---

## 2. PostgreSQL to Local Lakehouse CSV & Parquet

Extracts from a relational database and streams to partitioned CSV and Parquet files:

```yaml
id: postgres_to_csv
name: "Lakehouse Claims Export"
tenant_id: "finance_prod"

state_store:
  backend: mongodb
  database: veloctra_system

sources:
  - name: postgres_claims_source
    type: database
    connection_string: "postgresql+asyncpg://karthiksp@localhost:5432/healthcare_claims"
    query: "SELECT * FROM raw_claim_benef"
    chunk_size: 10000

destinations:
  - name: local_lakehouse_export
    type: file
    format: csv
    output_dir: "./output_claims_lakehouse"
    max_rows_per_file: 100000
    max_file_size_mb: 100
```

---

## 3. Multi-Destination Fan-Out with Field-Level AES Encryption

Extracts customer accounts, encrypts PII fields (SSN, credit card) using AES-256-GCM, and fans out to both MongoDB and AWS S3 Parquet:

```yaml
id: pii_secure_fanout
name: "PII Compliant Customer Fanout"
tenant_id: "fintech_compliance"

sources:
  - name: core_banking_mysql
    type: database
    connection_string: "mysql+aiomysql://app:secret@db.fintech.local:3306/banking"
    query: "SELECT account_id, customer_name, ssn, card_number, balance FROM accounts"
    chunk_size: 5000

encryption:
  fields_to_encrypt:
    - "ssn"
    - "card_number"

destinations:
  - name: mongo_analytics
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://mongo.internal:27017"
    database: "analytics"
    collection: "encrypted_customers"
    upsert_key: "account_id"

  - name: s3_secure_lakehouse
    type: file
    format: parquet
    output_dir: "s3://fintech-lakehouse-prod/encrypted_customers"
    max_rows_per_file: 50000
    max_file_size_mb: 50
```

---

## 4. Change Data Capture (CDC) High-Watermark Stream

Performs incremental delta sync from PostgreSQL to MongoDB with automatic watermark tracking:

```yaml
pipeline_id: pg_to_mongo_cdc_claims
project_id: healthcare_workspace
tenant_id: healthcare_workspace

settings:
  chunk_size: 5000
  dlq_enabled: true

sources:
  - name: postgres_raw_claims
    type: database
    connection_string: "postgresql+asyncpg://user:secret@postgres.internal:5432/claims_db"
    query: "SELECT id, beneficiary_id, amount, updated_at FROM claims"
    delta:
      watermark_column: "updated_at"
      watermark_type: "timestamp"
      initial_watermark: "2026-01-01T00:00:00"

destinations:
  - name: mongo_claims_live
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://mongo.internal:27017"
    database: "analytics_dw"
    collection: "claims"
    upsert_key: "id"
```

---

## 5. KEDA-Enabled Elastic Horizontal Autoscaling Pipeline

Scales worker pod count dynamically based on the discovered migration backlog size:

```yaml
pipeline_id: large_enterprise_migration
project_id: data_migration_prod
tenant_id: data_migration_prod

settings:
  chunk_size: 10000
  keda:
    enabled: true
    rows_per_worker: 100000     # 1 pod provisioned per 100,000 pending rows
    min_replicas: 1             # Baseline worker count (0 for scale-to-zero)
    max_replicas: 16            # Peak capacity during high migration volume

sources:
  - name: legacy_oracle_or_sql
    type: database
    connection_string: "postgresql+asyncpg://app:secret@db.prod:5432/legacy_dw"
    query: "SELECT * FROM enterprise_transactions"

destinations:
  - name: mongodb_atlas_cluster
    type: nosql
    db_type: mongodb
    connection_string: "mongodb+srv://admin:secret@atlas.mongodb.net"
    database: "enterprise_dw"
    collection: "transactions"
    upsert_key: "txn_id"
```

