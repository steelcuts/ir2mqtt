#!/bin/bash

echo "Starting IR2MQTT backend in Home Assistant Add-on mode..."

PORT=${APP_PORT:-${INGRESS_PORT:-8099}}

# Run pending database migrations
python3 -m alembic upgrade head

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"
