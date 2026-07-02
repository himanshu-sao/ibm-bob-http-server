#!/bin/bash

# Stop the IBM BOB HTTP server

set -e

PORT=31013
LOG_DIR="$HOME/.local/share/ibm-bob-http-server"

echo "⌛ Trying to stop IBM BOB HTTP Proxy Server (port $PORT)..."

# Find PID using port
PIDS=$(lsof -t -i :$PORT 2>/dev/null || echo "")

if [ -z "$PIDS" ]; then
    echo "🔍 No process found on port $PORT - server may not be running"
    exit 0
fi

# Kill each PID
for PID in $PIDS; do
    echo "🛑 Stopping process (PID: $PID)..."
    if kill -9 "$PID" 2>/dev/null; then
        echo "✅ Successfully stopped process $PID"
    else
        echo "❌ Failed to stop process $PID"
    fi
done

# Show recent logs if available (Check project logs first, then home dir logs)
PROJECT_LOG="logs/server.log"
if [ -f "$PROJECT_LOG" ]; then
    echo ""
    echo "📝 Last 30 lines from project log ($PROJECT_LOG):"
    tail -30 "$PROJECT_LOG"
elif [ -f "$LOG_DIR/server.log" ]; then
    echo ""
    echo "📝 Last 30 lines from system log ($LOG_DIR/server.log):"
    tail -30 "$LOG_DIR/server.log"
fi

echo ""
echo "🎉 Server stopped successfully"