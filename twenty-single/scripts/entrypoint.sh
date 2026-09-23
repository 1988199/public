#!/bin/sh
set -eu
umask 077
export PGDATA=/data/postgres
export NODE_PORT=3000 STORAGE_TYPE=local
mkdir -p /data/config /data/postgres /data/redis /data/twenty /run/twenty /run/postgresql
node /usr/local/lib/twenty-single/secrets.cjs
export POSTGRES_PASSWORD="$(cat /data/config/POSTGRES_PASSWORD)"
export APP_SECRET="$(cat /data/config/APP_SECRET)"
export ENCRYPTION_KEY="$(cat /data/config/ENCRYPTION_KEY)"
export PG_DATABASE_URL="$(node -e 'process.stdout.write(`postgres://postgres:${encodeURIComponent(process.env.POSTGRES_PASSWORD)}@127.0.0.1:5432/default`)')"
export REDIS_URL=redis://127.0.0.1:6379
chown -R postgres:postgres /data/postgres /run/postgresql
chown -R redis:redis /data/redis
chown -R node:node /data/twenty /run/twenty
chmod 700 /data/config /data/postgres
chmod 755 /run/postgresql
rm -f /run/twenty/initialized /run/twenty/worker-started

if [ -f "$PGDATA/PG_VERSION" ] && [ "$(cat "$PGDATA/PG_VERSION")" != 16 ]; then
  echo 'Unsupported PostgreSQL data version; perform a dump/restore migration to PostgreSQL 16.' >&2
  exit 1
fi
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo 'Initializing PostgreSQL 16 in /data/postgres'
  cp /data/config/POSTGRES_PASSWORD /run/postgresql/init-password
  chown postgres:postgres /run/postgresql/init-password
  su-exec postgres initdb -D "$PGDATA" --username=postgres --encoding=UTF8 --locale=C \
    --auth-local=peer --auth-host=scram-sha-256 --pwfile=/run/postgresql/init-password
  rm -f /run/postgresql/init-password
fi
# Starting a socket-only temporary database also repairs an interrupted first initialization.
su-exec postgres pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories=/run/postgresql" -w start
trap 'su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop || true' EXIT
if [ "$(su-exec postgres psql -h /run/postgresql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='default'")" != 1 ]; then
  su-exec postgres createdb -h /run/postgresql -U postgres default
fi
su-exec postgres pg_ctl -D "$PGDATA" -m fast -w stop
trap - EXIT
exec "$@"
