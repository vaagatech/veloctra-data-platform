# 🚀 Setup & Deployment Guide

This guide covers installing, configuring, and deploying the **Veloctra Data Platform** in development and production environments.

---

## 1. System Requirements

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+), macOS (Apple Silicon or Intel), or Windows (WSL2).
- **Python**: 3.10, 3.11, or 3.12
- **Node.js**: $\ge$ 18.0 (with npm $\ge$ 9.0)
- **State Store**: MongoDB $\ge$ 5.0 (Recommended for production) or SQLite (Default local fallback)
- **Target Databases**: PostgreSQL $\ge$ 13, MySQL $\ge$ 8.0, MongoDB $\ge$ 5.0

---

## 2. Local Monorepo Installation

### Clone the Repository
```bash
git clone git@github.com:vaagatech/veloctra-data-platform.git
cd veloctra-data-platform
```

### Python Virtual Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install all monorepo packages in editable mode
pip install -e packages/veloctra-core \
            -e packages/veloctra-security \
            -e packages/veloctra-state \
            -e packages/veloctra-resilience \
            -e packages/veloctra-connectors \
            -e packages/veloctra-transformers \
            -e packages/veloctra-orchestrator \
            -e packages/veloctra-api
```

### Frontend Build (Management Console)
```bash
cd apps/management-ui
npm install
npm run build
cd ../..
```

---

## 3. Environment Configuration (`.env`)

Create a `.env` file from the provided `.env.example`:

```bash
cp .env.example .env
```

Key environment variables:
```ini
# Application Server
PORT=8008
HOST=0.0.0.0
ENVIRONMENT=production
LOG_LEVEL=INFO

# State Backend (MongoDB recommended for production)
STATE_STORE_TYPE=mongodb
MONGO_DSN=mongodb://localhost:27017
MONGO_SYSTEM_DB=veloctra_system

# Security & Double Envelope Encryption
SECRET_KEY=supersecretjwtkey_replace_in_production
FERNET_PRIMARY_KEY=YOUR_BASE64_32_BYTE_FERNET_KEY
CHACHA_SECONDARY_KEY=YOUR_HEX_32_BYTE_CHACHA_KEY
```

---

## 4. Starting and Stopping the Engine

The platform includes production daemon control scripts:

### Start the Engine
```bash
PORT=8008 ./start.sh
```
Output:
```
==================================================================
 ⚡ Veloctra Engine — Enterprise ETL Platform Startup
==================================================================
🚀 Starting server daemon on http://localhost:8008...
==================================================================
 ✅ Veloctra Engine Started Successfully!
   - Management Console : http://localhost:8008
   - Login URL          : http://localhost:8008/login
   - REST API Docs      : http://localhost:8008/docs
   - Process PID        : 51553
   - Server Log File    : ./app.log
   - Credentials        : admin / changeme
==================================================================
```

### Stop the Engine Gracefully
```bash
./stop.sh
```

---

## 5. Docker Deployment

To run Veloctra inside a containerized environment:

```bash
docker-compose up -d --build
```
