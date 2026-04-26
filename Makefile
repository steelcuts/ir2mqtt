.PHONY: lint lint-frontend lint-backend \
        test-backend test-frontend test-e2e test-integration test-simulator test-simulator-gui \
        test check help dev-local dev setup update-deps clean migrate migration-create migrate-stamp migrate-check \
        docker-build docker-build-multi docker-run docker-stop \
        showcase doc-gifs docs-pdf

# Auto-detect Python: prefer local .venv, fall back to system python3
PYTHON ?= $(shell [ -f .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

# For venv creation and version checks: bypass any active venv and use pyenv directly if available
PYTHON3_BIN := $(shell command -v pyenv > /dev/null 2>&1 && pyenv which python3 2>/dev/null || command -v python3)

# Optional migration message
M ?= auto_migration

.DEFAULT_GOAL := help

IMAGE_TAG ?= ir2mqtt:local

help:
	@echo ""
	@echo "  make setup             		First-time setup (venv, pip, npm, husky)"
	@echo "  make update-deps       		Regenerate requirements.dev.txt for current Python version"
	@echo "  make lint              		Lint all code (frontend + backend)"
	@echo "  make lint-frontend     		Lint frontend only"
	@echo "  make lint-backend      		Lint backend with ruff (auto-fix)"
	@echo "  make find-untranslated 		Find untranslated strings in Vue files and output to CSV"
	@echo "  make test-backend      		Run backend unit tests"
	@echo "  make test-frontend     		Run frontend type-check + unit tests"
	@echo "  make test-e2e          		Run mocked E2E tests (manages backend lifecycle)"
	@echo "  make test-integration  		Run integration E2E tests (requires Docker)"
	@echo "  make test-simulator    		Run simulator unit tests (no GUI/display required)"
	@echo "  make test-simulator-gui  		Run simulator GUI tests (requires PyQt6 + display)"
	@echo "  make test              		Run backend + frontend + E2E tests"
	@echo "  make check             		Lint + all tests"
	@echo "  make clean             		Remove all files ignored by git (venv, node_modules, etc.)"
	@echo "  make migration-create  		Create a new migration script (usage: make migration-create m=\"message\")"
	@echo "  make migrate           		Apply all pending migrations"
	@echo "  make migrate-stamp     		Mark current database state as the latest (stamp head)"
	@echo "  make migrate-check     		Verify that models and migrations are in sync"
	@echo "  make docker-build        		Build Docker image for current platform (local testing)"
	@echo "  make docker-build-multi 		Build multi-platform image (linux/amd64 + linux/arm64, like CI)"
	@echo "  make docker-run         		Run the built image + Mosquitto (http://localhost:8099)"
	@echo "  make docker-stop        		Stop and remove the local test containers"
	@echo "  make showcase           		Generate a UI showcase video/GIF using Playwright"
	@echo "  make doc-gifs           		Generate per-feature GIFs for VitePress documentation"
	@echo "  make release VERSION=x.y.z		Set project version across all files and generate showcase"
	@echo "  make docs-dev           		Start local documentation server (VitePress)"
	@echo "  make docs-pdf           		Export VitePress documentation to ir2mqtt-docs.pdf"
	@echo ""

# ── First-time setup ──────────────────────────────────────────────────────────

setup: check-env
	@[ -d .venv ] || $(PYTHON3_BIN) -m venv .venv
	.venv/bin/pip install -q -e ".[dev]"
	cd frontend && npm install
	cd docs && npm install

check-env:
	@node -v | grep -E "v(2[2-9]|[3-9][0-9])\." > /dev/null || \
		(echo "Error: Node.js >= 22 is required. Current: $$(node -v)" && exit 1)
	@$(PYTHON3_BIN) --version | grep -E "3\.(12|13)" > /dev/null || \
		(echo "Warning: Recommended Python version is 3.12+. Current: $$($(PYTHON3_BIN) --version)")

build-all:
	make clean
	make setup
	make check
	docker compose build

# ── Docker image build ────────────────────────────────────────────────────────

# Build for the current platform only — fast, for local testing
docker-build:
	docker buildx build --load -t $(IMAGE_TAG) .

# Build for linux/amd64 + linux/arm64, exactly like CI (requires a buildx builder with multi-platform support)
docker-build-multi:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(IMAGE_TAG) .

# Run the built image together with a Mosquitto broker for local testing
docker-run:
	@docker network create ir2mqtt-test 2>/dev/null || true
	@docker run -d --name ir2mqtt-mqtt --network ir2mqtt-test \
		-p 1883:1883 \
		-v "$(PWD)/mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf" \
		eclipse-mosquitto:latest
	@docker run -d --name ir2mqtt-app --network ir2mqtt-test \
		-p 8099:8099 \
		-v "$(PWD)/data:/data" \
		-e MQTT_BROKER=ir2mqtt-mqtt \
		-e MQTT_PORT=1883 \
		$(IMAGE_TAG)
	@echo ""
	@echo "  Backend:  http://localhost:8099"
	@echo "  MQTT:     localhost:1883"
	@echo ""
	@echo "  Stop with: make docker-stop"

# Stop and remove local test containers
docker-stop:
	-docker stop ir2mqtt-app ir2mqtt-mqtt
	-docker rm   ir2mqtt-app ir2mqtt-mqtt
	-docker network rm ir2mqtt-test

update-deps:
	.venv/bin/pip install -q pip-tools
	.venv/bin/pip-compile --strip-extras --extra=dev --output-file=requirements.dev.txt pyproject.toml

# ── Local Development ─────────────────────────────────────────────────────────

dev:
	docker compose up

dev-local:
	@scripts/dev-local.sh

# ── Linting ───────────────────────────────────────────────────────────────────

lint-frontend:
	cd frontend && npm run lint

lint-backend:
	$(PYTHON) -m ruff check --fix backend tools
	$(PYTHON) -m ruff format backend tools

lint-simulator:
	$(PYTHON) -m ruff check --fix tools/simulator
	$(PYTHON) -m ruff format tools/simulator

find-untranslated:
	$(PYTHON) tools/find_untranslated_strings.py -o untranslated_strings.csv

# ── Unit tests ────────────────────────────────────────────────────────────────

test-backend:
	$(PYTHON) -m pytest backend/tests -p no:pytest-qt -q

test-simulator:
	$(PYTHON) -m pytest tools/simulator/tests -p no:pytest-qt -q \
		--ignore=tools/simulator/tests/test_simulator_gui.py

test-simulator-gui:
	$(PYTHON) -m pytest tools/simulator/tests/test_simulator_gui.py -q

test-frontend:
	cd frontend && npm run type-check && npm run test:run

# ── E2E tests ─────────────────────────────────────────────────────────────────

test-e2e:
	@echo "Running E2E tests..."
	@PORT=$${TEST_PORT:-8100}; \
	ROOT_DIR=$$(pwd); \
	cleanup() { echo "Cleaning up E2E test backend..."; "$$ROOT_DIR/scripts/stop-test-backend.sh"; }; \
	trap cleanup EXIT INT TERM; \
	echo "Starting test backend for E2E tests..."; \
	scripts/start-test-backend.sh "$$PORT"; \
	cd frontend && BACKEND_URL="http://127.0.0.1:$$PORT" npx playwright test --grep-invert @showcase

test-integration:
	cd frontend && npm run test:e2e:integration

showcase:
	@scripts/generate-gif.sh

doc-gifs:
	@scripts/generate-doc-gifs.sh $(FILTER)

release:
	@if [ -z "$(VERSION)" ]; then echo "Error: VERSION is not set. Usage: make release VERSION=1.0.0"; exit 1; fi
	@echo "Setting version to $(VERSION) in package.json, and pyproject.toml..."
	@$(PYTHON) -c "import json, re; \
	f='frontend/package.json'; d=json.load(open(f)); d['version']='$(VERSION)'; json.dump(d, open(f,'w'), indent=2); open(f,'a').write('\n'); \
	f='pyproject.toml'; c=open(f).read(); open(f,'w').write(re.sub(r'version = \".*\"', 'version = \"$(VERSION)\"', c, count=1))"
	@echo "Versions updated successfully. Running showcase..."
	@$(MAKE) showcase

# ── Documentation ─────────────────────────────────────────────────────────────

docs-dev:
	@echo "Starting local VitePress documentation server..."
	@npx vitepress dev docs

docs-pdf:
	@scripts/generate-docs-pdf.sh

# ── Combined ──────────────────────────────────────────────────────────────────

lint: lint-frontend lint-backend lint-simulator

test: test-backend test-frontend test-simulator test-simulator-gui test-e2e test-integration

check: lint test

clean:
	@echo "Cleaning up ignored files and directories..."
	git clean -fdX
	@echo "Project cleaned."

migration-create:
	@echo "Generating new migration with message: $(M)"
	$(PYTHON) -m alembic revision --autogenerate -m "$(M)"

migrate:
	@echo "Applying migrations..."
	$(PYTHON) -m alembic upgrade head

migrate-stamp:
	@echo "Stamping database with latest revision..."
	$(PYTHON) -m alembic stamp head

migrate-check:
	@echo "Checking if migrations are in sync with models..."
	$(PYTHON) -m alembic check
