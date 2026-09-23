#!/bin/sh
set -eu
until pg_isready -h 127.0.0.1 -U postgres -d default >/dev/null 2>&1 && [ "$(redis-cli ping 2>/dev/null)" = PONG ]; do sleep 2; done
if [ ! -f /run/twenty/initialized ]; then
  # Same commands as the official entrypoint, but migration/cron failures are fatal.
  if [ "${DISABLE_DB_MIGRATIONS:-false}" != true ]; then
    has_schema=$(psql "$PG_DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'core')")
    if [ "$has_schema" = f ]; then yarn database:init:prod; fi
    yarn command:prod cache:flush
    yarn command:prod upgrade
    yarn command:prod cache:flush
  fi
  if [ "${DISABLE_CRON_JOBS_REGISTRATION:-false}" != true ]; then
    yarn command:prod cron:register:all
  fi
  touch /run/twenty/initialized
fi
exec node dist/main
