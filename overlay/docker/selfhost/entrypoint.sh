#!/bin/sh
set -eu

cd /home/node/parabol

if [ "${1:-}" = "node" ] && [ "${2:-}" = "./dist/web.js" ]; then
  if [ -z "${SERVER_SECRET:-}" ] || [ -z "${POSTGRES_HOST:-}" ] || [ -z "${REDIS_URL:-}" ]; then
    echo "parabol: SERVER_SECRET, POSTGRES_*, and REDIS_URL must be set before start" >&2
    exit 1
  fi
  echo "parabol: running preDeploy (schema + query map)"
  node dist/preDeploy.js
fi

exec "$@"
