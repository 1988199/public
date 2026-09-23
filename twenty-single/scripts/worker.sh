#!/bin/sh
set -eu
until [ -f /run/twenty/initialized ] && curl -fsS --max-time 5 http://127.0.0.1:3000/healthz >/dev/null 2>&1; do sleep 2; done
touch /run/twenty/worker-started
exec yarn worker:prod
