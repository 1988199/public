#!/usr/bin/env bash
set -Eeuo pipefail

for process in mariadb redis gunicorn websocket worker scheduler nginx; do
  status="$(supervisorctl status "${process}" 2>/dev/null || true)"
  grep -Eq "^${process}[[:space:]]+RUNNING([[:space:]]|$)" <<<"${status}" || {
    echo "Supervisor 进程未运行：${process}（${status:-无状态}）" >&2
    exit 1
  }
done

curl --fail --silent --show-error --max-time 5 \
  -H "Host: ${SITE_NAME:-erp.localhost}" \
  http://127.0.0.1/api/method/ping >/dev/null
