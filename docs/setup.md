# Setup & Deployment Guide

## Prerequisites

- **Python**: 3.10+ (tested on Python 3.11)
- **Node.js**: 18+ (tested on Node 24.18)
- **Pip**: 23+

---

## Local Monorepo Setup

```bash
# 1. Clone workspace
cd /Users/karthiksp/projects/etl-sql-nosql

# 2. Install base dependencies
python3 -m pip install -r requirements.txt

# 3. Install Monorepo packages in editable mode
python3 -m pip install -e packages/etl-core \
                       -e packages/etl-security \
                       -e packages/etl-state \
                       -e packages/etl-resilience \
                       -e packages/etl-connectors \
                       -e packages/etl-transformers \
                       -e packages/etl-orchestrator \
                       -e packages/etl-api

# 4. Install & build React UI
cd apps/management-ui

npm install
npm run build
cd ../..
```

---

## Running the API & Management UI

Start the FastAPI server:

```bash
uvicorn enterprise_etl_engine.api.main:app --reload --port 8000
```

Open your browser to:
- **Management Console**: [http://localhost:8000/login](http://localhost:8000/login) (Default credentials: `admin` / `changeme`)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Running Tests

Execute the full 39-test unit suite:

```bash
python3 -m pytest tests/ -v
```

---

## Docker Deployment

Build and run via Docker:

```bash
# Build production container image
docker build -t enterprise-etl-engine:latest .

# Run container listening on port 8000
docker run -d -p 8000:8000 \
  -e APP_ENCRYPTION_KEY="your-32-byte-base64-key" \
  --name etl-engine enterprise-etl-engine:latest
```
