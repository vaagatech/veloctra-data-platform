#!/usr/bin/env zsh
# ==============================================================================
# Veloctra Engine — Application Startup Script
# Starts the Veloctra ETL Engine API server & React UI background daemon.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"
LOG_FILE="$SCRIPT_DIR/app.log"
PORT="${PORT:-8000}"

echo "=================================================================="
echo " ⚡ Veloctra Engine — Enterprise ETL Platform Startup"
echo "=================================================================="

# Step 1: Ensure .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    # Ensure a valid base64 32-byte encryption key is set
    if command -v python3 >/dev/null 2>&1; then
        KEY=$(python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())")
        sed -i '' "s|APP_ENCRYPTION_KEY=.*|APP_ENCRYPTION_KEY=$KEY|g" "$SCRIPT_DIR/.env" || true
    fi
    echo "✅ Created .env file."
fi

# Step 2: Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "❌ Veloctra Engine is already running (PID: $OLD_PID) on http://localhost:$PORT"
        echo "   Use './stop.sh' to terminate the running instance first."
        exit 1
    else
        echo "🧹 Removing stale PID file..."
        rm -f "$PID_FILE"
    fi
fi

# Step 3: Start FastAPI / Uvicorn server in background
echo "🚀 Starting server daemon on http://localhost:$PORT..."
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
fi

export PYTHONPATH="$SCRIPT_DIR/packages/veloctra-core:$SCRIPT_DIR/packages/veloctra-security:$SCRIPT_DIR/packages/veloctra-state:$SCRIPT_DIR/packages/veloctra-resilience:$SCRIPT_DIR/packages/veloctra-connectors:$SCRIPT_DIR/packages/veloctra-transformers:$SCRIPT_DIR/packages/veloctra-orchestrator:$SCRIPT_DIR/packages/veloctra-api:$SCRIPT_DIR"

nohup "$PYTHON_BIN" -m uvicorn veloctra_api.main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers 1 > "$LOG_FILE" 2>&1 &

NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# Step 4: Verify startup
sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "=================================================================="
    echo " ✅ Veloctra Engine Started Successfully!"
    echo "   - Management Console : http://localhost:$PORT"
    echo "   - Login URL          : http://localhost:$PORT/login"
    echo "   - REST API Docs      : http://localhost:$PORT/docs"
    echo "   - Process PID        : $NEW_PID"
    echo "   - Server Log File    : $LOG_FILE"
    echo "   - Credentials        : admin / changeme"
    echo "=================================================================="
    echo "   Use './stop.sh' to shutdown or 'tail -f app.log' to view logs."
else
    echo "❌ Server failed to start. Last logs:"
    tail -n 20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
