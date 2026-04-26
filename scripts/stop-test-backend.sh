#!/bin/sh
# Stop the isolated test backend started by start-test-backend.sh
# and clean up its temporary data directory.

PID_FILE=/tmp/ir2mqtt_test_backend.pid
DIR_FILE=/tmp/ir2mqtt_test_backend.dir

if [ -f "$PID_FILE" ]; then
  kill -9 "$(cat "$PID_FILE")" 2>/dev/null || true
  rm -f "$PID_FILE"
fi

if [ -f "$DIR_FILE" ]; then
  rm -rf "$(cat "$DIR_FILE")"
  rm -f "$DIR_FILE"
fi
