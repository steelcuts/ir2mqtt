#!/bin/sh
# Run the mocked (non-integration) E2E test suite.
# Manages the backend lifecycle — starts before tests, stops on exit.
#
# Usage: scripts/run-e2e.sh
#
# Environment:
#   TEST_PORT   Backend port (default: 8199)

set -e

PORT=${TEST_PORT:-8199}

cleanup() {
  scripts/stop-test-backend.sh
}
trap cleanup EXIT INT TERM

scripts/start-test-backend.sh "$PORT"

(cd frontend && BACKEND_URL="http://127.0.0.1:$PORT" npm run test:e2e)
