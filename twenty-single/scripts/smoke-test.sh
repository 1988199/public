#!/usr/bin/env bash
set -euo pipefail
image=${1:?Usage: smoke-test.sh IMAGE}
name="twenty-single-test-${RANDOM}"
volume="$name-data"
cleanup() {
  result=$?
  if (( result != 0 )); then docker logs --tail 250 "$name" || true; fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  exit "$result"
}
trap cleanup EXIT
wait_healthy() {
  for ((i=0; i<180; i++)); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$name")
    if [[ "$status" == healthy ]]; then return; fi
    if [[ $(docker inspect -f '{{.State.Running}}' "$name") != true ]]; then break; fi
    sleep 5
  done
  echo 'Container did not become healthy' >&2
  return 1
}
start() {
  docker run -d --name "$name" -e SERVER_URL=http://localhost:3000 \
    -v "$volume:/data" "$image" >/dev/null
  wait_healthy
}
sql() { docker exec -u postgres "$name" psql -h /run/postgresql -U postgres -d default -v ON_ERROR_STOP=1 "$@"; }
docker volume create "$volume" >/dev/null
start
docker exec "$name" curl -fsS http://localhost:3000/ | grep -qi '<html'
docker exec "$name" supervisorctl -c /etc/twenty-single/supervisord.conf status
sql -c "CREATE TABLE public.single_image_smoke (value text); INSERT INTO public.single_image_smoke VALUES ('persistent');"
docker exec "$name" redis-cli SET single-image-smoke persistent
docker exec -u node "$name" sh -c 'echo persistent > /data/twenty/smoke.txt'
secret_before=$(docker exec "$name" sha256sum /data/config/APP_SECRET /data/config/ENCRYPTION_KEY /data/config/POSTGRES_PASSWORD)
# Recreate the container, keeping only /data, to catch writes outside the volume.
docker stop -t 120 "$name" >/dev/null
docker rm "$name" >/dev/null
start
test "$(sql -tAc 'SELECT value FROM public.single_image_smoke')" = persistent
test "$(docker exec "$name" redis-cli GET single-image-smoke)" = persistent
test "$(docker exec "$name" cat /data/twenty/smoke.txt)" = persistent
test "$secret_before" = "$(docker exec "$name" sha256sum /data/config/APP_SECRET /data/config/ENCRYPTION_KEY /data/config/POSTGRES_PASSWORD)"
# Kill the actual worker process, and verify Supervisor replaces it.
worker_pid=$(docker exec "$name" supervisorctl -c /etc/twenty-single/supervisord.conf pid worker)
docker exec "$name" kill -KILL "$worker_pid"
sleep 20
worker_new_pid=$(docker exec "$name" supervisorctl -c /etc/twenty-single/supervisord.conf pid worker)
test "$worker_pid" != "$worker_new_pid"
docker exec "$name" /usr/local/lib/twenty-single/healthcheck.sh
echo 'PASS: HTTP, four services, PostgreSQL/Redis/files/secrets persistence, worker recovery'
