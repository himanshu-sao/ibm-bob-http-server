#!/bin/bash

# Start IBM BOB as Ollama-compatible HTTP server

set -e

echo "╔══════════════════════════════════════════════════════╗"
echo "║         IBM BOB → Ollama/LM Studio HTTP Proxy               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Configuration
PORT=31013
SERVER_FILE="server.py"
REQUIREMENTS_FILE="requirements-ollama.txt"

# Python Version Preference: 3.14 -> 3.11 -> 3
if command -v python3.14 &>/dev/null; then
    PYTHON_CMD="python3.14"
elif command -v python3.11 &>/dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ Python 3.11+ is required but not found"
    exit 1
fi

echo "Using Python: $($PYTHON_CMD --version)"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
    
    # Use the venv python for installation
    VENV_PYTHON=".venv/bin/python"
    echo "📦 Upgrading pip..."
    $VENV_PYTHON -m pip install --upgrade pip >/dev/null 2>&1
    echo "📦 Installing required packages..."
    $VENV_PYTHON -m pip install -r "$REQUIREMENTS_FILE" >/dev/null 2>&1
else
    VENV_PYTHON=".venv/bin/python"
fi

# Check if BOB is available
echo ""
echo "🔍 Checking IBM BOB Shell..."
if ! command -v bob &>/dev/null; then
    echo "⚠️ IBM BOB Shell (bob command) not found in PATH"
    echo "⚠️ Please install IBM BOB from https://bob.ibm.com before continuing"
    echo ""
    exit 1
else
    BOB_PATH=$(command -v bob)
    echo "✅ IBM BOB Shell found: $BOB_PATH"
fi

# Check if port is available
echo ""
echo "🔌 Checking port $PORT..."
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "⚠️ Port $PORT is already in use"
    echo "⚠️ Run './stop-ollama-proxy.sh' first or kill the existing process"
    LSOF_PID=$(lsof -t -i :$PORT)
    echo "PID using port: $LSOF_PID"
    echo "Try: kill -9 $LSOF_PID"
    exit 1
else
    echo "✅ Port $PORT is available"
fi

echo ""
echo "🚀 Starting IBM BOB HTTP Server..."
echo "≡ Serving OpenAI-compatible API on http://0.0.0.0:$PORT"
echo "≡ Ollama-compatible API on http://localhost:$PORT"
echo "≡ Models: ibm-bob-ollama, ibm-bob-chat, ibm-bob-code"
echo ""

# Create logs directory
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/server.log"

# Start the server using the Venv Python to ensure dependencies are loaded
nohup $VENV_PYTHON "$SERVER_FILE" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

echo ""
echo "✅ Server started in background (PID: $SERVER_PID)"
echo "📝 Logs are being written to: $LOG_FILE"
echo "🔌 API available at: http://localhost:$PORT"
echo ""
echo "🛑 To stop the server, run: ./stop-ollama-proxy.sh"
