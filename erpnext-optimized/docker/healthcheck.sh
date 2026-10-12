#!/usr/bin/env bash
set -Eeuo pipefail
for process in mariadb redis gunicorn websocket worker-short worker-long scheduler nginx; do
  supervisorctl status "$process" | grep -Eq "^${process}[[:space:]]+RUNNING"
done
redis-cli PING | grep -qx PONG
curl --fail --silent --show-error --max-time 5 -H "Host: ${SITE_NAME:-erp.localhost}" \
  http://127.0.0.1/api/method/frappe.ping | grep -q pong
cmp --silent /opt/erpnext-runtime/manifest.json \
  "/home/frappe/frappe-bench/sites/${SITE_NAME:-erp.localhost}/.optimized-runtime.json"
