# Testing & CI/CD

## Test Layers

| Layer | Command | Stack | What it tests |
|-------|---------|-------|---------------|
| Backend unit | `make test-backend` | Python only | API handlers, state logic, no IO |
| Frontend unit | `make test-frontend` | Node only | Stores, components — fully mocked |
| Mocked E2E | `make test-e2e` | Browser + real backend, no MQTT | Full UI flows against a real HTTP API |
| Integration E2E | `make test-integration` | Browser + backend + MQTT + sim | Full round-trip through MQTT with a virtual bridge |
| Simulator unit | `make test-simulator` | Python only | Simulator engine logic |
| Simulator GUI | `make test-simulator-gui` | Python + PyQt6 | Simulator GUI components |

Run `make check` to execute lint + all test layers before pushing.

---

## Mocked E2E Tests

Located in `frontend/e2e/*.spec.ts`. These use a real FastAPI backend (started automatically by `make test-e2e`) but **no MQTT broker** — the bridge list and MQTT status are mocked via Playwright `page.route()` and `page.routeWebSocket()`.

```bash
make test-e2e
# or with a custom port:
TEST_PORT=8200 make test-e2e
```

The backend is started on port 8199 by default, waits for it to be healthy, runs all specs, then shuts it down on exit. Doc-gif specs (`e2e/doc-gifs/`) are excluded from this run.

---

## Integration Tests

Located in `frontend/e2e/integration/`. These spin up a complete stack automatically:

1. **Mosquitto** via Docker (`eclipse-mosquitto:2`, port 18883)
2. **Backend** (FastAPI, port 8099, connected to Mosquitto)
3. **Sim-server** (`tools/sim_server.py`, port 8088) — HTTP API to spawn/control virtual IR bridges

```bash
make test-integration
# or directly:
cd frontend && npm run test:e2e:integration
```

To use a non-default Python binary:
```bash
PYTHON_BIN=/usr/bin/python3.12 make test-integration
```

### Sim-server API

Tests use `SimHelper` (from `e2e/integration/fixtures.ts`) to control virtual bridges:

```typescript
const bridge = await sim.spawn({ bridge_id: 'test-bridge-1' });  // create virtual bridge
await sim.inject({ bridge_id, protocol: 'nec', address: '0x04', command: '0x08' });  // inject IR signal
await sim.setLoopback(true);   // send → re-receive (round-trip test)
await sim.deleteAll();          // cleanup
```

---

## Doc-GIF Tests

Located in `frontend/e2e/doc-gifs/`. These record Playwright videos and convert them to GIFs for the VitePress documentation. They are **not** run during `make check` — only via `make doc-gifs`.

```bash
make doc-gifs               # generate all GIFs
make doc-gifs FILTER=bridges  # only regenerate docs/public/gifs/bridges.gif
```

`make doc-gifs` starts the same full stack as integration tests (Mosquitto + Backend + Sim-server), pre-spawns a virtual bridge, and seeds signal history. See [Local Setup — Generating doc GIFs](dev-setup#generating-doc-gifs) for prerequisites.

---

## Bridge Simulator (GUI / CLI)

Located in `tools/simulator/`. Simulates ESPHome IR bridges over MQTT without physical hardware — useful for manual testing during development.

```bash
cd tools/simulator

# GUI (requires PyQt6)
./run_gui.sh        # macOS/Linux
run_gui.bat         # Windows

# CLI
./run_cli.sh --broker localhost
./run_cli.sh --broker localhost --port 1883 --data ../../data --clean
```

---

## Git Hooks

Managed by Husky, run automatically on commit and push.

| Hook | Trigger | What runs |
|------|---------|-----------|
| `pre-commit` | `git commit` | ESLint, vue-tsc, vitest, ruff, pytest, Playwright mocked E2E |
| `pre-push` | `git push` | Integration E2E tests (requires Docker) |

The pre-push hook skips gracefully when Docker is unavailable (prints a warning instead of blocking).

---

## CI/CD Pipeline

Defined in `.github/workflows/ci.yaml`. Runs on every push and pull request.

| Job | Runs on | What it does |
|-----|---------|-------------|
| `lint` | all pushes | ESLint + ruff |
| `test-backend` | all pushes | pytest backend + simulator |
| `test-frontend` | all pushes | vue-tsc + vitest |
| `test-integration` | all pushes | Full Playwright integration suite (Docker) |
| `docker-build` | `main` + `v*.*.*` tags | Builds and pushes multi-platform image to `ghcr.io` |

The Docker image is only published on pushes to `main` or version tags (`v*.*.*`). See [Release Process](dev-setup#release-process) for the full tagging workflow.
