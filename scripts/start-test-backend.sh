#!/bin/sh
# Start an isolated backend for E2E testing.
#
# Usage: scripts/start-test-backend.sh [PORT]
#
# State files (cleaned up by stop-test-backend.sh):
#   /tmp/ir2mqtt_test_backend.pid  — PID of the uvicorn process
#   /tmp/ir2mqtt_test_backend.dir  — path to the temp data directory
#
# Environment:
#   PYTHON_BIN  Override the Python executable (default: .venv/bin/python3
#               if present, otherwise system python3)

set -e

PORT=${1:-8100}

# Resolve Python executable
if [ -n "$PYTHON_BIN" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -f ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

# Kill any leftover process on this port
if command -v lsof >/dev/null 2>&1; then
  lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true
fi

# Isolated data directory
DATA_DIR=$(mktemp -d)
echo "$DATA_DIR" > /tmp/ir2mqtt_test_backend.dir

# Start backend (no MQTT — mocked E2E only needs the HTTP API)
IRDB_PATH="$DATA_DIR/ir_db" \
OPTIONS_FILE="$DATA_DIR/options.yaml" \
DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/ir2mqtt.db" \
APP_ENV=development \
  "$PYTHON" -m uvicorn backend.main:app \
    --host 127.0.0.1 --port "$PORT" > /dev/null 2>&1 &

echo $! > /tmp/ir2mqtt_test_backend.pid

printf "⏳ Waiting for backend on port %s..." "$PORT"
counter=0
until curl -fs "http://127.0.0.1:$PORT/api/status" > /dev/null 2>&1; do
  if [ $counter -ge 30 ]; then
    echo ""
    echo "❌ Backend did not start within 30 seconds on port $PORT" >&2
    kill -9 "$(cat /tmp/ir2mqtt_test_backend.pid)" 2>/dev/null || true
    rm -rf "$DATA_DIR" /tmp/ir2mqtt_test_backend.pid /tmp/ir2mqtt_test_backend.dir
    exit 1
  fi
  printf "."
  counter=$((counter + 1))
  sleep 1
done

echo " ready (PID $(cat /tmp/ir2mqtt_test_backend.pid))"
