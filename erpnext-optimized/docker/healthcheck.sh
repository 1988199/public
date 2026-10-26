#!/usr/bin/env bash
set -Eeuo pipefail
# 同一轮一次读取所有状态，避免每15秒启动10次Python管理进程；缺项、重复或非RUNNING均失败。
processes='mariadb redis gunicorn websocket worker-short worker-long scheduler nginx backup-service logrotate-service'
statuses="$(supervisorctl status $processes)"
awk -v expected="$processes" '
  BEGIN { n=split(expected, names, " "); for (i=1;i<=n;i++) wanted[names[i]]=1 }
  { if (!($1 in wanted) || $2 != "RUNNING" || seen[$1]++) bad=1; count++ }
  END { exit (bad || count != n) }
' <<<"$statuses"
redis-cli PING | grep -qx PONG
curl --fail --silent --show-error --max-time 5 -H "Host: ${SITE_NAME:-erp.localhost}" \
  http://127.0.0.1/api/method/frappe.ping | grep -q pong
cmp --silent /opt/erpnext-runtime/manifest.json \
  "/home/frappe/frappe-bench/sites/${SITE_NAME:-erp.localhost}/.optimized-runtime.json"
sudo -E -H -u frappe /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/readiness.py probe >/dev/null
