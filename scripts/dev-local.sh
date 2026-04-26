#!/bin/sh
# Starts the IR2MQTT stack for local development on macOS/Linux.
# - Mosquitto runs in Docker (via docker-compose)
# - Backend runs natively on the host (can access /dev/cu.* serial ports)
# - Frontend runs natively on the host via Vite

set -e

# Resolve Python executable
if [ -f ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

echo "🐳 Starting Mosquitto via Docker Compose..."
docker-compose up -d mqtt-broker

echo "🐍 Starting Backend natively (with hot-reload)..."
mkdir -p data
DATABASE_URL="sqlite+aiosqlite:///$PWD/data/ir2mqtt.db" \
IRDB_PATH="$PWD/data/ir_db" \
OPTIONS_FILE="$PWD/data/options.yaml" \
MQTT_BROKER=localhost \
MQTT_PORT=1883 \
APP_ENV=development "$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port 8099 --reload --reload-dir backend &
BACKEND_PID=$!

echo "⚛️  Starting Frontend natively (Vite)..."
(cd frontend && BACKEND_URL=http://127.0.0.1:8099 npm run dev) &
FRONTEND_PID=$!

echo ""
echo "🚀 Stack is running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8099"
echo "   MQTT:     localhost:1883"
echo ""
echo "Press Ctrl+C to stop everything."

# Cleanup on exit
trap "echo 'Stopping stack...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; docker-compose stop mqtt-broker" INT TERM EXIT

# Wait for background processes
wait
