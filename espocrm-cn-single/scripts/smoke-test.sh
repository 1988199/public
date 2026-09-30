#!/usr/bin/env bash
# 只使用本次创建的临时容器和卷，核对初始化、网页和重新创建后的持久化。
set -Eeuo pipefail
image="${1:?用法: smoke-test.sh IMAGE}"
name="espocrm-test-${GITHUB_RUN_ID:-local}-${RANDOM}"
volume="${name}-data"
cleanup() {
  result=$?
  # 避免入口日志中的默认凭据进入公开 CI 日志。
  if (( result != 0 )); then
    docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$name" || true
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  exit "$result"
}
trap cleanup EXIT
wait_ready() {
  for _ in $(seq 1 180); do
    if docker exec "$name" sh -c 'test -f /var/www/html/data/config.php && curl -fsS -H "Accept: text/html" http://127.0.0.1/ >/dev/null' 2>/dev/null; then
      installed=$(docker exec -u www-data "$name" php /var/www/html/bin/command config:get isInstalled)
      if [[ "$installed" == true ]]; then return; fi
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$name")" != true ]]; then break; fi
    sleep 5
  done
  echo 'EspoCRM 首次启动检查失败' >&2
  return 1
}
start() {
  docker run -d --name "$name" -v "$volume:/data" "$image" >/dev/null
  wait_ready
}
docker volume create "$volume" >/dev/null
start
docker exec "$name" sh -c 'echo persistent > /data/espocrm/custom/smoke.txt'
config_before=$(docker exec "$name" sha256sum /data/espocrm/data/config.php)
docker stop -t 120 "$name" >/dev/null
docker rm "$name" >/dev/null
start
test "$(docker exec "$name" cat /data/espocrm/custom/smoke.txt)" = persistent
test "$config_before" = "$(docker exec "$name" sha256sum /data/espocrm/data/config.php)"
docker exec -u www-data "$name" php /var/www/html/bin/command config:get language | grep -qx zh_CN
echo 'PASS: 安装、HTTP、中文配置、容器重建后的文件和配置持久化'
