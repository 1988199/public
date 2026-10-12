#!/usr/bin/env bash
set -Eeuo pipefail
image="${1:?image}"
previous="${2:?base image}"
prefix="optimized-ci-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
site=ci.localhost
password="$(openssl rand -hex 24)"
echo "::add-mask::$password"
temp="$(mktemp -d)"
cleanup() {
  for name in "$prefix-fresh" "$prefix-old" "$prefix-upgrade" "$prefix-guard"; do
    docker rm -f -v "$name" >/dev/null 2>&1 || true
  done
  rm -rf "$temp"
}
trap cleanup EXIT
wait_healthy() {
  local name="$1"
  for _ in {1..120}; do
    status="$(docker inspect --format '{{.State.Health.Status}}' "$name")"
    [[ "$status" != healthy ]] || return 0
    [[ "$(docker inspect --format '{{.State.Running}}' "$name")" == true ]] || break
    sleep 5
  done
  docker logs "$name" | tail -100
  return 1
}
run_fresh() {
  docker run -d --name "$prefix-fresh" --stop-timeout 300 \
    -e SITE_NAME="$site" -e INIT_SITE=1 -e DB_ROOT_PASSWORD="$password" -e ADMIN_PASSWORD="$password" "$image"
  wait_healthy "$prefix-fresh"
  docker cp tests/site_checks.py "$prefix-fresh:/tmp/site_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/site_checks.py
  docker exec -u frappe "$prefix-fresh" /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/test_sqlite.py
  docker cp tests/web_checks.py "$prefix-fresh:/tmp/web_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" -e CI_SITE_PASSWORD="$password" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/web_checks.py
  before="$(docker logs "$prefix-fresh" 2>&1 | grep -c 'Migrating ' || true)"
  docker restart --time 300 "$prefix-fresh"
  wait_healthy "$prefix-fresh"
  after="$(docker logs "$prefix-fresh" 2>&1 | grep -c 'Migrating ' || true)"
  [[ "$before" == "$after" ]]
  docker logs "$prefix-fresh" 2>&1 | grep -q '版本一致：跳过'
  docker logs "$prefix-fresh" 2>&1 | tail -150 | grep -q 'Shutdown complete'
  docker exec "$prefix-fresh" supervisorctl status | tee "$temp/services.txt"
  grep -q '^worker-short.*RUNNING' "$temp/services.txt"
  grep -q '^worker-long.*RUNNING' "$temp/services.txt"
}
run_upgrade() {
  docker run -d --name "$prefix-old" --stop-timeout 300 -e SITE_NAME="$site" \
    -e DB_ROOT_PASSWORD="$password" -e ADMIN_PASSWORD="$password" "$previous"
  wait_healthy "$prefix-old"
  docker stop --time 300 "$prefix-old"
  docker run -d --name "$prefix-guard" --volumes-from "$prefix-old" -e SITE_NAME="$site" "$image"
  for _ in {1..90}; do
    [[ "$(docker inspect --format '{{.State.Running}}' "$prefix-guard")" == true ]] || break
    sleep 2
  done
  [[ "$(docker inspect --format '{{.State.Running}}' "$prefix-guard")" == false ]]
  docker logs "$prefix-guard" 2>&1 | grep -q 'RUN_MIGRATIONS=1'
  docker run -d --name "$prefix-upgrade" --stop-timeout 300 --volumes-from "$prefix-old" \
    -e SITE_NAME="$site" -e RUN_MIGRATIONS=1 "$image"
  wait_healthy "$prefix-upgrade"
  docker exec "$prefix-upgrade" find "/home/frappe/frappe-bench/sites/$site/private/runtime_backups" -name manifest.json | grep -q manifest
  docker cp tests/site_checks.py "$prefix-upgrade:/tmp/site_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-upgrade" \
    /home/frappe/frappe-bench/env/bin/python /tmp/site_checks.py
}
run_fresh
run_upgrade
echo '全新初始化、真实物料索引、重启跳过迁移、正常停机、升级保护及迁移前备份检查通过'
