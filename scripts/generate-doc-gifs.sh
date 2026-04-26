#!/bin/sh
# Generate doc GIFs for the VitePress documentation.
#
# Starts a full simulation stack (Mosquitto + Backend + Sim-server), pre-spawns
# a virtual bridge, then runs the Playwright doc-gif specs. Each spec records
# its own video which is converted to a GIF in docs/public/gifs/.
#
# Usage:
#   scripts/generate-doc-gifs.sh           # generate all GIFs
#   scripts/generate-doc-gifs.sh devices   # generate only docs/public/gifs/devices.gif
#
# Prerequisites: ffmpeg + Docker must be installed.
# Output: docs/public/gifs/*.gif  (checked into the repo so VitePress can serve them)

set -e

ROOT_DIR="$(pwd)"
FILTER="${1:-}"

# ── Ports ─────────────────────────────��─────────────────────────────────────────
BACKEND_PORT=8199
SIM_PORT=8091
MQTT_PORT=18891
MOSQUITTO_CONTAINER="ir2mqtt-docgif-mosquitto"

# Pre-spawned bridge (used by all specs)
BRIDGE_ID="living-room-node"

# Resolve Python executable
if [ -n "$PYTHON_BIN" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -f ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

# ── PID / state files ───────────────────────────────────────────────────────────
BACKEND_PID_FILE=/tmp/ir2mqtt_docgif_backend.pid
SIM_PID_FILE=/tmp/ir2mqtt_docgif_sim.pid
DATA_DIR_FILE=/tmp/ir2mqtt_docgif_data.dir

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

# ── 1. Mosquitto via Docker ─────────────────────────────────────────────────────
echo "▶  Starting Mosquitto on port $MQTT_PORT..."
docker run -d --rm --name "$MOSQUITTO_CONTAINER" \
  -p "${MQTT_PORT}:1883" \
  eclipse-mosquitto:2 \
  mosquitto -c /mosquitto-no-auth.conf
sleep 2
echo "   Mosquitto ready."

# ── 2. Backend with MQTT ────────────────────────────────────────────────────────
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

# ── 4. Sim-server ───────────────────────────────────────────────────────────────
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

# ── 5. Pre-spawn bridge + seed history ─────────────────────────────────────────
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

echo "▶  Injecting IR history signals..."
for payload in \
  '{"bridge_id":"'"$BRIDGE_ID"'","protocol":"nec","address":"0x0707","command":"0x02"}' \
  '{"bridge_id":"'"$BRIDGE_ID"'","protocol":"samsung","address":"0xE0E0","command":"0x40BF"}' \
  '{"bridge_id":"'"$BRIDGE_ID"'","protocol":"nec","address":"0x0707","command":"0x08"}'; do
  curl -sf -X POST "http://127.0.0.1:$SIM_PORT/inject" \
    -H "Content-Type: application/json" \
    -d "$payload" > /dev/null
  sleep 0.3
done
echo "   History seeded."

# ── 6. Run Playwright doc-gif specs ────────────────────────────────────────────
echo "▶  Running doc-gif Playwright tests..."
cd frontend

if [ -n "$FILTER" ]; then
  BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" \
  SIM_URL="http://127.0.0.1:$SIM_PORT" \
  BRIDGE_ID="$BRIDGE_ID" \
    npx playwright test \
      --config=playwright.doc-gifs.config.ts \
      --grep "doc-gif: $FILTER"
else
  BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" \
  SIM_URL="http://127.0.0.1:$SIM_PORT" \
  BRIDGE_ID="$BRIDGE_ID" \
    npx playwright test \
      --config=playwright.doc-gifs.config.ts
fi

cd "$ROOT_DIR"

# ── 6. Convert each recorded video to a GIF ────────────────────────────────────
# ── 7. Convert each recorded video to a GIF ───────────────────────────────────
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "⚠  ffmpeg not found — skipping GIF conversion."
  echo "   Videos are in: frontend/test-results/doc-gifs/"
  exit 0
fi

mkdir -p docs/public/gifs

CONVERTED=0
FAILED=0

for gif_dir in frontend/test-results/doc-gifs/*/; do
  [ -d "$gif_dir" ] || continue

  name="$(basename "$gif_dir")"

  if [ -n "$FILTER" ] && [ "$name" != "$FILTER" ]; then
    continue
  fi

  webm="$(find "$gif_dir" -name "*.webm" | head -n 1)"
  if [ -z "$webm" ]; then
    echo "  ⚠  No video found in $gif_dir — skipping $name"
    FAILED=$((FAILED + 1))
    continue
  fi

  out="docs/public/gifs/${name}.gif"
  echo "  🎞  Converting $name → $out"

  ffmpeg -y -ss 0.8 -i "$webm" \
    -vf "fps=15,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
    -loop 0 \
    "$out" 2>/dev/null

  size="$(du -sh "$out" | cut -f1)"
  echo "     ✓ $out ($size)"
  CONVERTED=$((CONVERTED + 1))
done

echo ""
echo "Done. $CONVERTED GIF(s) generated in docs/public/gifs/"
if [ "$FAILED" -gt 0 ]; then
  echo "  ⚠  $FAILED spec(s) produced no video — check Playwright output above."
fi
