#!/usr/bin/env bash
set -Eeuo pipefail
/home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/maintenance.py ready
exec "$@"
