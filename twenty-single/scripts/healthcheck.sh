#!/bin/sh
set -eu
test -f /run/twenty/initialized
test -f /run/twenty/worker-started
curl -fsS --max-time 5 http://127.0.0.1:3000/healthz >/dev/null
pg_isready -h 127.0.0.1 -U postgres -d default >/dev/null
test "$(redis-cli ping)" = PONG
supervisorctl -c /etc/twenty-single/supervisord.conf status | \
  awk '$2 != "RUNNING" { bad=1 } END { exit (bad || NR != 4) }'
