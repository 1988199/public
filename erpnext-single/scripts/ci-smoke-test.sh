#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:?用法: ci-smoke-test.sh <image>}"
container="myerp-ci-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
site_name="${CI_SITE_NAME:-ci.localhost}"
previous_image="${2:-}"
previous_container="${container}-previous"

cleanup() {
  docker rm -f -v "${container}" >/dev/null 2>&1 || true
  docker rm -f -v "${previous_container}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_healthy() {
  local target="$1"
  for _ in $(seq 1 120); do
    if [[ "$(docker inspect --format '{{.State.Health.Status}}' "$target")" == healthy ]]; then
      return 0
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "$target")" != true ]]; then
      break
    fi
    sleep 10
  done
  docker logs "$target" >&2
  return 1
}

# 上一版仅初始化合成空站点；备份后使用同一组临时卷执行升级。
volume_args=()
if [[ -n "$previous_image" ]]; then
  docker run --detach --name "$previous_container" \
    --env SITE_NAME="$site_name" "$previous_image" >/dev/null
  wait_healthy "$previous_container"
  docker exec "$previous_container" bash -lc \
    "cd /home/frappe/frappe-bench && sudo -H -u frappe /home/frappe/.local/bin/bench --site '$site_name' backup --with-files"
  docker stop --time 120 "$previous_container" >/dev/null
  volume_args=(--volumes-from "$previous_container")
fi

site_env_args=()
if [[ "${CI_OMIT_SITE_NAME:-0}" != 1 ]]; then
  site_env_args=(--env SITE_NAME="${site_name}")
fi
docker run --detach "${volume_args[@]}" \
  --name "${container}" \
  "${site_env_args[@]}" \
  "${image}" >/dev/null

status=starting
for _ in $(seq 1 120); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container}")"
  case "${status}" in
    healthy)
      break
      ;;
    unhealthy)
      echo "容器健康检查失败。" >&2
      docker logs "${container}" >&2
      exit 1
      ;;
  esac

  if [[ "$(docker inspect --format '{{.State.Running}}' "${container}")" != "true" ]]; then
    echo "容器在完成初始化前退出。" >&2
    docker logs "${container}" >&2
    exit 1
  fi
  sleep 10
done

if [[ "${status}" != "healthy" ]]; then
  echo "容器未在 20 分钟内进入 healthy 状态，最后状态：${status}" >&2
  docker logs "${container}" >&2
  exit 1
fi

login_result="$(docker exec "${container}" curl --fail --silent --show-error \
  --header "Host: localhost" \
  --request POST \
  --data 'usr=Administrator' \
  --data 'pwd=Pass1234' \
  http://127.0.0.1/api/method/login)"
grep -Fq '"message":"Logged In"' <<<"${login_result}"

apps="$(docker exec "${container}" bash -lc \
  "cd /home/frappe/frappe-bench && sudo -H -u frappe /home/frappe/.local/bin/bench --site '${site_name}' list-apps")"
printf '%s\n' "${apps}"

grep -Eq '^erpnext([[:space:]]|$)' <<<"${apps}"
grep -Eq '^hrms([[:space:]]|$)' <<<"${apps}"
grep -Eq '^crm([[:space:]]|$)' <<<"${apps}"
grep -Eq '^china_sme_accounting([[:space:]]|$)' <<<"${apps}"
frappe_ref="$(sed -n 's/^ARG FRAPPE_REF=//p' Dockerfile)"
for app in frappe erpnext hrms crm; do
  if [[ "$app" == frappe ]]; then
    version="${frappe_ref#v}"
  else
    version="$(jq -r --arg app "$app" '.[] | select(.name == $app) | .ref | ltrimstr("v")' docker/apps.json)"
  fi
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
  actual_version="$(awk -v expected_app="$app" '$1 == expected_app {print $2}' <<<"${apps}")"
  [[ "$actual_version" == "$version" ]]
done
grep -Eq '^china_sme_accounting[[:space:]]+0\.2\.0([[:space:]]|$)' <<<"${apps}"

chart_test="$(docker exec "${container}" bash -lc \
  "cd /home/frappe/frappe-bench && sudo -H -u frappe /home/frappe/.local/bin/bench --site '${site_name}' execute china_sme_accounting.tests.smoke.run")"
printf '%s\n' "${chart_test}"
grep -Fq '"template_visible": true' <<<"${chart_test}"
grep -Fq '"empty_site_verified": true' <<<"${chart_test}"
grep -Fq '"numbered_accounts": 66' <<<"${chart_test}"

localization_test="$(docker exec "${container}" bash -lc \
  "cd /home/frappe/frappe-bench && sudo -H -u frappe /home/frappe/.local/bin/bench --site '${site_name}' execute china_sme_accounting.tests.localization.run")"
printf '%s\n' "${localization_test}"
grep -Fq '"language": "zh"' <<<"${localization_test}"
grep -Fq '"required_translation_count": 10' <<<"${localization_test}"
grep -Fq '"key_translations_verified": true' <<<"${localization_test}"

docker exec "${container}" curl --fail --silent --show-error \
  --header "Host: localhost" \
  http://127.0.0.1/api/method/ping >/dev/null

for process in mariadb redis gunicorn websocket worker scheduler nginx; do
  docker exec "${container}" supervisorctl status "${process}" |
    grep -Eq "^${process}[[:space:]]+RUNNING([[:space:]]|$)"
done

docker cp scripts/check-image-web.py "${container}:/tmp/check-image-web.py"
docker exec "$container" /home/frappe/frappe-bench/env/bin/python /tmp/check-image-web.py "$site_name"

echo "镜像烟雾测试通过：容器健康，服务进程正常，全部 App 已安装，关键简体中文译文有效。"
