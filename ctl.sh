#!/usr/bin/env zsh
# ==============================================================================
# Veloctra Engine — Unified Control Manager CLI
# Usage: ./ctl.sh {start|stop|restart|status|logs}
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/app.pid"
LOG_FILE="$SCRIPT_DIR/app.log"

case "$1" in
    start)
        "$SCRIPT_DIR/start.sh"
        ;;
    stop)
        "$SCRIPT_DIR/stop.sh"
        ;;
    restart)
        echo "Restarting Veloctra Engine..."
        "$SCRIPT_DIR/stop.sh"
        sleep 1
        "$SCRIPT_DIR/start.sh"
        ;;
    status)
        echo "=================================================================="
        echo " ⚡ Veloctra Engine Status"
        echo "=================================================================="
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            PID=$(cat "$PID_FILE")
            echo " Status      : 🟢 RUNNING"
            echo " Process PID : $PID"
            echo " Web Console : http://localhost:${PORT:-8008}"
            echo " Log File    : $LOG_FILE"
        else
            echo " Status      : 🔴 STOPPED"
        fi
        echo "=================================================================="
        ;;
    logs)
        if [ -f "$LOG_FILE" ]; then
            echo "Tailing log file: $LOG_FILE (Press Ctrl+C to exit)"
            tail -f "$LOG_FILE"
        else
            echo "No log file found at $LOG_FILE"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
