#!/usr/bin/env bashio

echo "Starting IR2MQTT backend in Home Assistant Add-on mode..."

# Default port
PORT=8099

if bashio::config.has 'ingress_port'; then
    PORT=$(bashio::addon.ingress_port)
    echo "Using Ingress port ${PORT}."
fi

# Run pending database migrations
python3 -m alembic upgrade head

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}"