#!/bin/sh
# Generate the showcase GIF for the README / GitHub assets.
#
# Starts a full simulation stack (Mosquitto + Backend + Sim-server), pre-spawns
# a virtual bridge and downloads the IR database, then runs the Playwright
# showcase spec. The recorded video is converted to a GIF.
#
# Usage: scripts/generate-gif.sh
#
# Prerequisites: ffmpeg + Docker must be installed.
# Output: .github/assets/showcase.gif

set -e

ROOT_DIR="$(pwd)"

# ── Ports ──────────────────────────────────────────────────────────────────────
BACKEND_PORT=8198
SIM_PORT=8092
MQTT_PORT=18892
MOSQUITTO_CONTAINER="ir2mqtt-showcase-mosquitto"

# Pre-spawned bridge
BRIDGE_ID="living-room-node"

# Resolve Python executable
if [ -n "$PYTHON_BIN" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -f ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

# ── PID / state files ──────────────────────────────────────────────────────────
BACKEND_PID_FILE=/tmp/ir2mqtt_showcase_backend.pid
SIM_PID_FILE=/tmp/ir2mqtt_showcase_sim.pid
DATA_DIR_FILE=/tmp/ir2mqtt_showcase_data.dir

cleanup() {
  echo "▶  Stopping services..."

  if [ -f "$BACKEND_PID_FILE" ]; then
    kill -9 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
    rm -f "$BACKEND_PID_FILE"
  fi

  if [ -f "$SIM_PID_FILE" ]; then
    kill -9 "$(cat "$SIM_PID_FILE")" 2>/dev/null || true
    rm -f "$SIM_PID_FILE"
  fi

  docker rm -f "$MOSQUITTO_CONTAINER" 2>/dev/null || true

  if [ -f "$DATA_DIR_FILE" ]; then
    rm -rf "$(cat "$DATA_DIR_FILE")"
    rm -f "$DATA_DIR_FILE"
  fi
}
trap cleanup EXIT INT TERM

# Kill any leftover processes from a previous run
lsof -ti :"$BACKEND_PORT" | xargs kill -9 2>/dev/null || true
lsof -ti :"$SIM_PORT"     | xargs kill -9 2>/dev/null || true
docker rm -f "$MOSQUITTO_CONTAINER" 2>/dev/null || true

# ── 1. Mosquitto via Docker ────────────────────────────────────────────────────
echo "▶  Starting Mosquitto on port $MQTT_PORT..."
docker run -d --rm --name "$MOSQUITTO_CONTAINER" \
  -p "${MQTT_PORT}:1883" \
  eclipse-mosquitto:2 \
  mosquitto -c /mosquitto-no-auth.conf
sleep 2
echo "   Mosquitto ready."

# ── 2. Backend with MQTT ───────────────────────────────────────────────────────
echo "▶  Starting backend on port $BACKEND_PORT..."
DATA_DIR=$(mktemp -d)
echo "$DATA_DIR" > "$DATA_DIR_FILE"

DATABASE_URL="sqlite+aiosqlite:///$DATA_DIR/ir2mqtt.db" \
MQTT_BROKER=127.0.0.1 \
MQTT_PORT="$MQTT_PORT" \
APP_MODE=standalone \
APP_ENV=development \
LOG_LEVEL=WARNING \
OPTIONS_FILE="$DATA_DIR/options.yaml" \
  "$PYTHON" -m uvicorn backend.main:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" > /dev/null 2>&1 &
echo $! > "$BACKEND_PID_FILE"

printf "   Waiting for backend..."
counter=0
until curl -fs "http://127.0.0.1:$BACKEND_PORT/api/status" > /dev/null 2>&1; do
  [ $counter -ge 30 ] && echo " TIMEOUT" && exit 1
  printf "."; counter=$((counter + 1)); sleep 1
done

printf " waiting for MQTT..."
counter=0
until curl -fs "http://127.0.0.1:$BACKEND_PORT/api/status" | grep -q '"mqtt_connected": *true'; do
  [ $counter -ge 20 ] && echo " TIMEOUT (MQTT did not connect)" && exit 1
  printf "."; counter=$((counter + 1)); sleep 1
done
echo " ready."

# ── 3. IR Database ─────────────────────────────────────────────────────────────
echo "▶  Downloading IR database (this takes ~60s)..."
curl -sf -X POST "http://127.0.0.1:$BACKEND_PORT/api/irdb/sync" \
  -H "Content-Type: application/json" \
  -d '{"flipper": true, "probono": true}' > /dev/null

printf "   Waiting for IR database..."
counter=0
until curl -fs "http://127.0.0.1:$BACKEND_PORT/api/irdb/status" | grep -q '"exists": *true'; do
  [ $counter -ge 180 ] && echo " TIMEOUT" && exit 1
  printf "."; counter=$((counter + 1)); sleep 1
done
echo " ready."

# ── 4. Sim-server ──────────────────────────────────────────────────────────────
echo "▶  Starting sim-server on port $SIM_PORT..."
"$PYTHON" "$ROOT_DIR/tools/sim_server.py" \
  --broker 127.0.0.1 \
  --mqtt-port "$MQTT_PORT" \
  --port "$SIM_PORT" > /dev/null 2>&1 &
echo $! > "$SIM_PID_FILE"

printf "   Waiting for sim-server..."
counter=0
until curl -fs "http://127.0.0.1:$SIM_PORT/health" > /dev/null 2>&1; do
  [ $counter -ge 20 ] && echo " TIMEOUT" && exit 1
  printf "."; counter=$((counter + 1)); sleep 1
done
echo " ready."

# ── 5. Pre-spawn bridge ────────────────────────────────────────────────────────
echo "▶  Spawning virtual bridge '$BRIDGE_ID'..."
curl -sf -X POST "http://127.0.0.1:$SIM_PORT/spawn" \
  -H "Content-Type: application/json" \
  -d "{\"bridge_id\": \"$BRIDGE_ID\"}" > /dev/null

printf "   Waiting for bridge to come online..."
counter=0
until curl -fs "http://127.0.0.1:$BACKEND_PORT/api/bridges" | grep -q '"online"'; do
  [ $counter -ge 30 ] && echo " TIMEOUT" && exit 1
  printf "."; counter=$((counter + 1)); sleep 1
done
echo " online."

# ── 6. Run Playwright showcase test ───────────────────────────────────────────
echo "▶  Running Playwright showcase test..."
cd frontend
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" \
SIM_URL="http://127.0.0.1:$SIM_PORT" \
BRIDGE_ID="$BRIDGE_ID" \
  npm run test:e2e:showcase
cd "$ROOT_DIR"

# ── 7. Convert video to GIF ────────────────────────────────────────────────────
echo "Looking for generated video..."
VIDEO_FILE=$(find frontend/test-results -name "*.webm" | head -n 1)

if [ -z "$VIDEO_FILE" ]; then
  echo "Error: No video file found in test-results directory."
  exit 1
fi

echo "Found video: $VIDEO_FILE"
mkdir -p .github/assets
GIF_FILE=".github/assets/showcase.gif"

if command -v ffmpeg >/dev/null 2>&1; then
  echo "Converting video to GIF using ffmpeg..."
  ffmpeg -y -ss 1.5 -i "$VIDEO_FILE" \
    -vf "fps=15,scale=1024:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
    -loop 0 "$GIF_FILE"
  echo "GIF successfully generated at $(realpath "$GIF_FILE")"
else
  echo "Warning: ffmpeg is not installed. Skipping GIF conversion."
  cp "$VIDEO_FILE" .github/assets/showcase.webm
  echo "Video copied to .github/assets/showcase.webm"
fi
