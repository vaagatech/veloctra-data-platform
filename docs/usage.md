# Usage & API Reference

## Demo Applications & Benchmarks

The `apps/demos/` directory contains standalone executable applications for all core scenarios:

### 1. Generate Synthetic Datasets (10MB to 1GB+)
```bash
# Generate a 50MB test dataset
python3 apps/demos/generate_synthetic_data.py --size-mb 50 --output test_50mb.db
```

### 2. Demo 1: High-Volume Relational to Parquet Stream
```bash
python3 apps/demos/demo_sql_to_parquet.py
```
*Outputs auto-partitioned Parquet files with field-level AES-256-GCM encryption.*

### 3. Demo 2: In-Flight Field Encryption & Decryption
```bash
python3 apps/demos/demo_encrypted_migration.py
```
*Verifies AES-256-GCM encryption & decryption roundtrip.*

### 4. Demo 3: High-Volume Benchmark & Adaptive MemoryGuard
```bash
python3 apps/demos/demo_delta_high_volume.py
```
*Processes 320,000+ rows (50MB+) at ~120,000 rows/sec with zero memory leaks.*

---

## API Reference

### Auth Endpoints
- `POST /auth/login` — Obtain JWT access token.
- `POST /auth/refresh` — Refresh token.
- `GET /auth/me` — Current user profile.

### Configuration Endpoints
- `GET /configs/{project_id}` — Get pipeline configuration (secrets masked).
- `PUT /configs/{project_id}` — Create or update YAML configuration with schema validation.
- `POST /configs/{project_id}/validate` — Dry-run JSON Schema validation.

### Pipeline Controls
- `POST /pipelines/{job_id}/start` — Trigger orchestrator job.
- `POST /pipelines/{job_id}/pause` — Pause pipeline state.
- `POST /pipelines/{job_id}/resume` — Resume pipeline from latest checkpoint.
- `GET /pipelines/{job_id}/status` — Status, FSM state & Circuit Breakers.
- `GET /pipelines/{job_id}/dlq` — List Dead Letter Queue records.
- `POST /pipelines/{job_id}/dlq/replay` — Replay DLQ records.

### Real-Time Telemetry
- `WS /ws/telemetry/{project_id}?token=<JWT>` — Live progress, memory %, state transitions & circuit breaker events.
