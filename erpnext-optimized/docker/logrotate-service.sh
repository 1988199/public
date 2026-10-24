#!/usr/bin/env bash
set -Eeuo pipefail
trap 'exit 0' TERM INT
while true; do
  /usr/sbin/logrotate --state /home/frappe/frappe-bench/logs/.runtime-logrotate.status \
    /opt/erpnext-runtime/logrotate.conf
  sleep 60 &
  wait "$!"
done
