# 📖 Usage & Pipeline Management

Veloctra provides two primary ways to create, manage, and execute pipelines:
1. **Interactive Visual Studio (Web Console)**
2. **REST API & CI/CD Pipelines**

---

## 1. Visual Pipeline Studio

Access the web studio at [http://localhost:8008/studio](http://localhost:8008/studio) (Default credentials: `admin` / `changeme`).

### Key Capabilities in Pipeline Studio:
- **Pipeline Selector**: Switch seamlessly between existing pipelines.
- **Visual & YAML Editor**: Edit sources, destinations, transform rules, and enrichments visually or in raw YAML with automatic schema validation.
- **1-Click Publish**: Click **"Publish to Engine"** to push the pipeline definition into the MongoDB state store and automatically register encrypted database connections.
- **Trigger Execution**: Start pipelines with one click and monitor live telemetry in real-time.

---

## 2. REST API Integration

All platform capabilities are exposed via OpenAPI/Swagger compliant REST endpoints:

### Authenticate
```bash
TOKEN=$(curl -s -X POST http://localhost:8008/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "changeme"}' | jq -r .access_token)
```

### Start a Pipeline
```bash
curl -s -X POST http://localhost:8008/pipelines/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"pipeline_id": "csv_to_postgres"}' | jq .
```

### Query Live Telemetry
```bash
curl -s http://localhost:8008/metrics/live | jq .
```
Response:
```json
{
  "cpu_percent": 18.5,
  "cpu_cores": 8,
  "memory_used_gb": 12.4,
  "memory_total_gb": 16.0,
  "memory_available_gb": 3.6,
  "memory_percent": 77.5,
  "threads_count": 24,
  "proc": {
    "rss_mb": 145.2,
    "cpu_percent": 12.0
  },
  "state_store": {
    "type": "mongodb",
    "status": "connected"
  }
}
```

### List Encrypted Connections
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8008/configs/connections/list | jq .
```

---

## 3. Real-Time WebSockets Telemetry

Connect to `/ws/telemetry/{job_id}?token={jwt_token}` to receive sub-second chunk progress, row throughput, MemoryGuard events, and FSM transitions.
