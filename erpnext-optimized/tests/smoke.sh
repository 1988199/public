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
  for name in "$prefix-fresh" "$prefix-old" "$prefix-upgrade" "$prefix-guard" "$prefix-restore"; do
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
  docker run -d --name "$prefix-fresh" --stop-timeout 600 \
    --mount type=volume,target=/runtime-copy \
    -e BACKUP_START_DELAY_SECONDS=1 -e BACKUP_INTERVAL_SECONDS=60 \
    -e SITE_NAME="$site" -e INIT_SITE=1 -e DB_ROOT_PASSWORD="$password" -e ADMIN_PASSWORD="$password" "$image"
  wait_healthy "$prefix-fresh"
  docker cp tests/site_checks.py "$prefix-fresh:/tmp/site_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/site_checks.py
  docker exec -u frappe "$prefix-fresh" /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/test_sqlite.py
  docker cp tests/web_checks.py "$prefix-fresh:/tmp/web_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" -e CI_SITE_PASSWORD="$password" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/web_checks.py
  # 只暂停合成测试容器的备份服务，避免手动回归与定时任务竞争；不启动cron。
  automatic_ok=0
  for _ in {1..60}; do
    if docker exec -u frappe "$prefix-fresh" /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/backup_service.py status | \
      python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if data.get("last_success",0)>0 else 1)'; then
      automatic_ok=1
      break
    fi
    sleep 2
  done
  [[ "$automatic_ok" == 1 ]]
  docker exec "$prefix-fresh" supervisorctl stop backup-service
  docker inspect "$prefix-fresh" --format '{{json .Mounts}}' | \
    /usr/bin/python3 -c 'import json,sys; assert any(x["Type"] == "volume" and x["Destination"] == "/runtime-copy" for x in json.load(sys.stdin))'
  docker cp tests/runtime_checks.py "$prefix-fresh:/tmp/runtime_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/runtime_checks.py
  docker exec "$prefix-fresh" supervisorctl start backup-service
  docker exec "$prefix-fresh" supervisorctl stop logrotate-service
  docker exec "$prefix-fresh" logrotate --force --state /tmp/runtime-logrotate-check.status /opt/erpnext-runtime/logrotate.conf
  docker exec "$prefix-fresh" test -s /home/frappe/frappe-bench/logs/nginx/access.log.1
  docker exec "$prefix-fresh" supervisorctl start logrotate-service
  CI_SITE_PASSWORD="$password" python3 tests/restore_check.py --source "$prefix-fresh" \
    --target "$prefix-restore" --image "$image" --site "$site"
  docker cp tests/busy_worker.py "$prefix-fresh:/tmp/busy_worker.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-fresh" \
    /home/frappe/frappe-bench/env/bin/python /tmp/busy_worker.py
  before="$(docker logs "$prefix-fresh" 2>&1 | grep -c 'Migrating ' || true)"
  started="$(date +%s)"
  docker restart --timeout 600 "$prefix-fresh"
  [[ "$(($(date +%s) - started))" -ge 15 ]]
  [[ "$(docker inspect --format '{{.Config.StopTimeout}}' "$prefix-fresh")" == 600 ]]
  wait_healthy "$prefix-fresh"
  after="$(docker logs "$prefix-fresh" 2>&1 | grep -c 'Migrating ' || true)"
  [[ "$before" == "$after" ]]
  # 不用 grep -q 提前关闭管道，避免日志增多时 pipefail 将 SIGPIPE 当成失败。
  docker logs "$prefix-fresh" 2>&1 | grep -F '版本一致：跳过' >/dev/null
  docker logs "$prefix-fresh" 2>&1 | grep -F 'Shutdown complete' >/dev/null
  if docker logs "$prefix-fresh" 2>&1 | grep -E 'killing .*SIGKILL' >/dev/null; then exit 1; fi
  docker exec "$prefix-fresh" supervisorctl status | tee "$temp/services.txt"
  grep -q '^worker-short.*RUNNING' "$temp/services.txt"
  grep -q '^worker-long.*RUNNING' "$temp/services.txt"
}
run_upgrade() {
  docker run -d --name "$prefix-old" --stop-timeout 600 -e SITE_NAME="$site" \
    -e DB_ROOT_PASSWORD="$password" -e ADMIN_PASSWORD="$password" "$previous"
  wait_healthy "$prefix-old"
  docker stop --timeout 600 "$prefix-old"
  docker run -d --name "$prefix-guard" --volumes-from "$prefix-old" -e SITE_NAME="$site" "$image"
  for _ in {1..90}; do
    [[ "$(docker inspect --format '{{.State.Running}}' "$prefix-guard")" == true ]] || break
    sleep 2
  done
  [[ "$(docker inspect --format '{{.State.Running}}' "$prefix-guard")" == false ]]
  docker logs "$prefix-guard" 2>&1 | grep -F 'RUN_MIGRATIONS=1' >/dev/null
  docker run -d --name "$prefix-upgrade" --stop-timeout 600 --volumes-from "$prefix-old" \
    -e SITE_NAME="$site" -e RUN_MIGRATIONS=1 "$image"
  wait_healthy "$prefix-upgrade"
  docker exec "$prefix-upgrade" find "/home/frappe/frappe-bench/sites/$site/private/runtime_backups" -name manifest.json | grep -F manifest >/dev/null
  docker cp tests/site_checks.py "$prefix-upgrade:/tmp/site_checks.py"
  docker exec -u frappe -e SITE_NAME="$site" "$prefix-upgrade" \
    /home/frappe/frappe-bench/env/bin/python /tmp/site_checks.py
}
run_fresh
run_upgrade
echo '全新初始化、真实物料索引、重启跳过迁移、正常停机、升级保护及迁移前备份检查通过'
