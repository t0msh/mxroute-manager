#!/bin/sh
set -e

# Ensure persistent paths exist and are owned by the app user when started as root.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/logs
    chown -R app:app /data
    exec gosu app "$@"
fi

exec "$@"
