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
