/**
 * Integration test global setup.
 *
 * Starts (in order):
 *   1. Mosquitto via Docker on port 18883
 *   2. IR2MQTT FastAPI backend on port 8099 (python subprocess)
 *   3. IR2MQTT Simulator control server on port 8088 (python subprocess)
 *
 * PIDs/container names written to .pids.json for teardown.
 * Runtime URLs written to .runtime.json for tests.
 */

import { spawn, execSync, type ChildProcess } from 'child_process';
import { writeFileSync, mkdirSync, existsSync, rmSync } from 'fs';
import { join, resolve } from 'path';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// ─── Constants ───────────────────────────────────────────────────────────────
export const MOSQUITTO_PORT    = 18883;
export const BACKEND_PORT      = 8099;
export const SIM_PORT          = 8088;
const MOSQUITTO_CONTAINER_NAME = 'ir2mqtt-test-mosquitto';

const PROJECT_ROOT = resolve(__dirname, '../../..');
// Override with PYTHON_BIN env var for CI, uv, poetry, conda, or Windows.
const VENV_PYTHON  = process.env.PYTHON_BIN ?? join(PROJECT_ROOT, '.venv/bin/python3');
const RUNTIME_FILE = join(__dirname, '.runtime.json');
const PIDS_FILE    = join(__dirname, '.pids.json');
const TMP_DIR      = join(tmpdir(), 'ir2mqtt_integration');

// ─── Helpers ─────────────────────────────────────────────────────────────────

function log(msg: string) {
  process.stdout.write(`[setup] ${msg}\n`);
}

async function waitForHttp(url: string, timeoutMs = 30_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status < 500) return;
    } catch { /* still starting */ }
    await new Promise(r => setTimeout(r, 400));
  }
  throw new Error(`Timeout (${timeoutMs}ms) waiting for ${url}`);
}

async function waitForMqttConnected(backendUrl: string, timeoutMs = 20_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${backendUrl}/api/status`);
      if (res.ok) {
        const data = await res.json() as { mqtt_connected: boolean };
        if (data.mqtt_connected) return;
      }
    } catch { /* still connecting */ }
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(`Backend MQTT did not connect within ${timeoutMs}ms`);
}

function spawnDetached(
  cmd: string,
  args: string[],
  opts: { env?: Record<string, string> } = {},
): ChildProcess {
  const proc = spawn(cmd, args, {
    cwd: PROJECT_ROOT,
    env: { ...process.env, ...(opts.env ?? {}) },
    detached: true,
    stdio: 'ignore',
  });
  proc.unref();
  return proc;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default async function globalSetup() {
  // Kill any leftover processes from a previous interrupted run
  execSync(`lsof -ti :${BACKEND_PORT} | xargs kill -9 2>/dev/null || true`, { stdio: 'ignore', shell: true });
  execSync(`lsof -ti :${SIM_PORT} | xargs kill -9 2>/dev/null || true`, { stdio: 'ignore', shell: true });
  execSync(`docker rm -f ${MOSQUITTO_CONTAINER_NAME} 2>/dev/null || true`, { stdio: 'ignore' });
  await new Promise(r => setTimeout(r, 300));

  mkdirSync(join(TMP_DIR, 'data'), { recursive: true });
  mkdirSync(join(TMP_DIR, 'ir_db'), { recursive: true });

  const dbPath = join(TMP_DIR, 'ir2mqtt_test.db');
  if (existsSync(dbPath)) rmSync(dbPath);

  const pids: number[] = [];

  // ── 1. Mosquitto via Docker ──────────────────────────────────────────────
  log(`Starting Mosquitto (Docker) on port ${MOSQUITTO_PORT}…`);

  // Remove any leftover container from a previous interrupted run
  execSync(`docker rm -f ${MOSQUITTO_CONTAINER_NAME} 2>/dev/null || true`, { stdio: 'ignore' });

  execSync(
    `docker run -d --rm --name ${MOSQUITTO_CONTAINER_NAME} \
      -p ${MOSQUITTO_PORT}:1883 \
      eclipse-mosquitto:2 \
      mosquitto -c /mosquitto-no-auth.conf`,
    { stdio: 'ignore' },
  );

  // Wait until the broker actually accepts connections
  await new Promise(r => setTimeout(r, 1500));
  log('Mosquitto container started.');

  // ── 2. Backend ────────────────────────────────────────────────────────────
  log(`Starting Backend on port ${BACKEND_PORT}…`);
  const backend = spawnDetached(
    VENV_PYTHON,
    ['-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', String(BACKEND_PORT)],
    {
      env: {
        DATABASE_URL:     `sqlite+aiosqlite:///${dbPath}`,
        MQTT_BROKER:      '127.0.0.1',
        MQTT_PORT:        String(MOSQUITTO_PORT),
        APP_MODE:         'standalone',
        APP_ENV:          'development',
        LOG_LEVEL:        'WARNING',
        IRDB_PATH:        join(TMP_DIR, 'ir_db'),
        OPTIONS_FILE:     join(TMP_DIR, 'data', 'options.yaml'),
      },
    },
  );
  if (backend.pid) pids.push(backend.pid);
  await waitForHttp(`http://localhost:${BACKEND_PORT}/api/status`);
  await waitForMqttConnected(`http://localhost:${BACKEND_PORT}`);
  log('Backend ready (MQTT connected).');

  // ── 3. Simulator control server ───────────────────────────────────────────
  log(`Starting Simulator on port ${SIM_PORT}…`);
  const simServer = spawnDetached(
    VENV_PYTHON,
    [
      join(PROJECT_ROOT, 'tools/sim_server.py'),
      '--broker', '127.0.0.1',
      '--mqtt-port', String(MOSQUITTO_PORT),
      '--port', String(SIM_PORT),
    ],
  );
  if (simServer.pid) pids.push(simServer.pid);
  await waitForHttp(`http://localhost:${SIM_PORT}/health`);
  log('Simulator ready.');

  // ── Write runtime info ────────────────────────────────────────────────────
  writeFileSync(PIDS_FILE, JSON.stringify({ pids, dockerContainers: [MOSQUITTO_CONTAINER_NAME] }));
  writeFileSync(RUNTIME_FILE, JSON.stringify({
    mosquittoPort: MOSQUITTO_PORT,
    backendUrl:    `http://localhost:${BACKEND_PORT}`,
    simUrl:        `http://localhost:${SIM_PORT}`,
    tmpDir:        TMP_DIR,
  }, null, 2));

  log('All services up — running tests.');
}
