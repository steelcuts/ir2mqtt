# Local Setup & Architecture

## Project Structure

```text
ir2mqtt/
├── backend/              # FastAPI application (Python)
│   ├── routers/          # API endpoints (devices, bridges, automations, …)
│   ├── tests/            # Backend unit tests (pytest)
│   └── main.py           # App entrypoint
├── frontend/             # Vue 3 + Vite + TypeScript
│   ├── src/
│   │   ├── stores/       # Pinia stores (one per domain)
│   │   ├── views/        # Page-level components
│   │   └── components/   # Shared components
│   └── e2e/
│       ├── *.spec.ts     # Mocked E2E tests (Playwright)
│       ├── doc-gifs/     # Playwright specs that record GIFs for the docs
│       └── integration/  # Full-stack integration tests (real MQTT)
├── tools/
│   ├── simulator/        # PyQt6 GUI + CLI for simulating IR bridges
│   └── sim_server.py     # HTTP control server for integration/doc-gif tests
├── docs/                 # VitePress documentation site
│   └── public/gifs/      # Auto-generated GIFs (committed, served by VitePress)
├── scripts/              # Dev/CI shell scripts
└── Makefile              # Task runner — run `make help` for all targets
```

## First-time Setup

```bash
make setup
```

Creates `.venv`, installs Python dependencies (`pip install -e ".[dev]"`), runs `npm install` in `frontend/`, and activates Husky git hooks.

::: warning Node & Python versions
Node.js ≥ 22 and Python 3.12+ are required. `make setup` will abort if Node is too old.
:::

## Starting the Dev Server

```bash
make dev          # Full stack via Docker Compose (backend + frontend + MQTT)
make dev-local    # Native processes + Mosquitto in Docker (needed for Mac serial port access)
```

`dev-local` is preferred on macOS because Docker Desktop can't expose USB serial ports to containers.

---

## All Make Targets

Run `make help` at any time for a quick reference.

### Development

| Command | What it does |
|---------|-------------|
| `make setup` | First-time setup — venv, pip, npm, Husky hooks |
| `make dev` | Start full stack via Docker Compose |
| `make dev-local` | Start backend + frontend natively, Mosquitto in Docker |
| `make update-deps` | Regenerate `requirements.dev.txt` for the current Python version |

### Linting

| Command | What it does |
|---------|-------------|
| `make lint` | Lint everything (frontend + backend + simulator) |
| `make lint-frontend` | ESLint with auto-fix on `frontend/` |
| `make lint-backend` | Ruff check + format on `backend/` and `tools/` |

### Testing

| Command | What it does |
|---------|-------------|
| `make test-backend` | pytest `backend/tests/` |
| `make test-frontend` | vue-tsc type check + vitest unit tests |
| `make test-e2e` | Playwright mocked E2E — starts a temporary backend automatically |
| `make test-integration` | Full-stack integration tests (requires Docker for Mosquitto) |
| `make test-simulator` | Simulator unit tests (no display required) |
| `make test-simulator-gui` | Simulator GUI tests (requires PyQt6 + display) |
| `make test` | All of the above |
| `make check` | `lint` + `test` — run this before pushing |

### Database Migrations

| Command | What it does |
|---------|-------------|
| `make migrate` | Apply all pending Alembic migrations |
| `make migrate-check` | Verify models and migrations are in sync |
| `make migrate-stamp` | Mark the current DB state as up-to-date without running migrations |
| `make migration-create M="message"` | Generate a new migration from model changes |

Always run `make migrate-check` before opening a PR that touches SQLAlchemy models. If it reports a diff, run `make migration-create M="describe_change"` and commit the generated file.

### Docker

| Command | What it does |
|---------|-------------|
| `make docker-build` | Build image for the current platform (fast, for local testing) |
| `make docker-build-multi` | Build for `linux/amd64` + `linux/arm64` (like CI) |
| `make docker-run` | Run the built image + Mosquitto at `http://localhost:8099` |
| `make docker-stop` | Stop and remove the local test containers |

### Documentation

| Command | What it does |
|---------|-------------|
| `make docs-dev` | Start local VitePress server at `http://localhost:5173` |
| `make doc-gifs` | Generate all documentation GIFs (requires Docker + ffmpeg) |
| `make showcase` | Generate the UI showcase GIF |

#### Generating doc GIFs

`make doc-gifs` starts a full simulation stack (Mosquitto + backend with MQTT + sim-server), pre-spawns a virtual IR bridge, runs the Playwright recording specs, and converts each `.webm` to an optimised `.gif` in `docs/public/gifs/`.

```bash
make doc-gifs               # regenerate all GIFs
make doc-gifs FILTER=bridges  # regenerate only docs/public/gifs/bridges.gif
```

Prerequisites: Docker and `ffmpeg` must be installed.

---

## Release Process

Releases follow semantic versioning (`MAJOR.MINOR.PATCH`). The steps below bump the version everywhere it is recorded, generate a fresh showcase GIF, and tag the commit.

### 1. Bump the version

```bash
make release VERSION=1.2.0
```

This updates the version string in:
- `config.json`
- `frontend/package.json`
- `pyproject.toml`

…and then runs `make showcase` to regenerate the showcase GIF.

### 2. Run the full check

```bash
make check
```

All tests and linters must be green before tagging.

### 3. Regenerate doc GIFs (optional but recommended)

```bash
make doc-gifs
```

Commit the updated GIFs alongside the version bump so the docs stay in sync.

### 4. Commit and tag

```bash
git add -A
git commit -m "chore: release v1.2.0"
git tag v1.2.0
git push origin main --tags
```

Pushing a `v*.*.*` tag triggers the CI pipeline which builds and pushes the multi-platform Docker image to `ghcr.io`.

::: tip Hotfixes
For a hotfix on an older release, branch off the relevant tag (`git checkout -b hotfix/1.1.1 v1.1.0`), apply the fix, then run `make release VERSION=1.1.1` on that branch.
:::

---

## Environment Variables

The backend reads the following variables at startup (all optional in development):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ir2mqtt.db` | SQLAlchemy async URL |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `APP_MODE` | `standalone` | `standalone` or `ha_app` |
| `APP_ENV` | `production` | `development` enables auto-reload |
| `LOG_LEVEL` | `INFO` | uvicorn / app log level |
| `IRDB_PATH` | `./data/ir_db` | Path to the IR database files |
| `OPTIONS_FILE` | `./data/options.yaml` | HA app options file path |

In `make dev-local` and `make test-e2e` these are set automatically via the startup scripts.

---

## Firmware (ir2mqtt_bridge)

The ESPHome bridge firmware lives in a separate **ir2mqtt_bridge** repository. Below is a quick reference for contributors working on the component.

### Project Structure

```text
ir2mqtt_bridge/
├── components/
│   └── ir2mqtt_bridge/        # Core component folder
│       ├── __init__.py        # Python config & code-generation logic
│       ├── ir2mqtt_bridge.h   # C++ header
│       └── ir2mqtt_bridge.cpp # C++ implementation
├── examples/                  # Ready-to-use YAML configurations
└── MANUAL.md                  # Detailed firmware documentation
```

ESPHome requires component logic inside `components/<name>/`. The `__init__.py` acts as the bridge between YAML configuration and the generated C++ code.

### Continuous Integration

On every push to `main` and every PR, a GitHub Actions workflow:
1. Installs ESPHome.
2. Creates a dummy `secrets.yaml`.
3. Patches the example files to use the local component code.
4. Compiles all four example configurations (`lan`, `wifi`, `serial`, `multi_serial`).

This ensures changes to the C++ code or configuration schema don't silently break the provided examples.

### Technical Notes

#### Why no `mqtt_id` in the config?

The MQTT client is a **global component** in ESPHome — there is always exactly one instance (`mqtt::global_mqtt_client`). The `__init__.py` auto-detects whether MQTT is present in the YAML and wires it up automatically, keeping the user configuration clean.

#### Conditional compilation: `USE_UART`, `USE_MQTT`, `USE_LIGHT`

When ESPHome parses your YAML, `__init__.py` checks which features are active and injects compiler flags (e.g. `cg.add_define("USE_UART")`). The C++ code wraps feature logic in `#ifdef` blocks:

```cpp
#ifdef USE_UART
  // Only compiled if uart_id is set
#endif
```

Features that aren't configured are never compiled into the firmware, keeping the binary as small as possible.
