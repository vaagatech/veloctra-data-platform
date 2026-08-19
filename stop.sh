#!/usr/bin/env zsh
# ==============================================================================
# Veloctra Engine — Application Shutdown Script
# Gracefully terminates the running Veloctra ETL Engine daemon.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"

echo "=================================================================="
echo " 🛑 Veloctra Engine — Graceful Shutdown"
echo "=================================================================="

# Function to stop by PID
stop_pid() {
    local PID=$1
    if kill -0 "$PID" 2>/dev/null; then
        echo "Sending SIGTERM to Veloctra Engine process (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
        
        # Wait up to 10 seconds for graceful shutdown
        for i in {1..10}; do
            if ! kill -0 "$PID" 2>/dev/null; then
                echo "✅ Process $PID stopped gracefully."
                return 0
            fi
            sleep 1
        done

        # Force kill if still alive
        if kill -0 "$PID" 2>/dev/null; then
            echo "⚠️ Process $PID did not stop in time. Sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
            echo "✅ Process $PID force terminated."
        fi
    fi
}

STOPPED=0

# 1. Stop by PID file
if [ -f "$PID_FILE" ]; then
    TARGET_PID=$(cat "$PID_FILE")
    stop_pid "$TARGET_PID"
    rm -f "$PID_FILE"
    STOPPED=1
fi

# 2. Check for any leftover uvicorn processes matching enterprise_etl_engine
LEFTOVER_PIDS=$(ps aux | grep "[v]eloctra_api.main:app" | awk '{print $2}')

if [ -n "$LEFTOVER_PIDS" ]; then
    echo "Found active uvicorn background processes: $LEFTOVER_PIDS"
    for pid in $LEFTOVER_PIDS; do
        stop_pid "$pid"
    done
    STOPPED=1
fi

if [ $STOPPED -eq 1 ]; then
    echo "=================================================================="
    echo " ✅ Veloctra Engine has been stopped."
    echo "=================================================================="
else
    echo "ℹ️  No running instance of Veloctra Engine was found."
fi
