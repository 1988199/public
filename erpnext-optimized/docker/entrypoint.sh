#!/usr/bin/env bash
set -Eeuo pipefail

BENCH_DIR=/home/frappe/frappe-bench
SITE_NAME="${SITE_NAME:-erp.localhost}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-Pass1234}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Pass1234}"
for key in DB_ROOT_PASSWORD ADMIN_PASSWORD; do
  file_key="${key}_FILE"
  if [[ -n "${!file_key:-}" ]]; then
    # 密码文件优先于环境变量及镜像默认值。
    [[ -r "${!file_key}" ]] || { echo "密码文件不可读取。" >&2; exit 1; }
    printf -v "$key" '%s' "$(cat "${!file_key}")"
  fi
done
export SITE_NAME

if [[ ! "$SITE_NAME" =~ ^[a-z0-9][a-z0-9.-]*$ ]]; then
  echo "SITE_NAME 只能包含小写字母、数字、点和连字符。" >&2
  exit 1
fi

# 浏览器使用 localhost，内部仍可沿用持久卷中既有的站点名。
envsubst '${SITE_NAME}' </etc/nginx/nginx.conf.template >/etc/nginx/nginx.conf
nginx -t

fresh_site=0
fresh_database=0
if [[ ! -f "$BENCH_DIR/sites/$SITE_NAME/site_config.json" ]]; then
  [[ "${INIT_SITE:-1}" == 1 ]] || { echo '站点不存在，且 INIT_SITE=0 禁止初始化。' >&2; exit 1; }
  if find "$BENCH_DIR/sites" -mindepth 2 -maxdepth 2 -name site_config.json -print -quit 2>/dev/null | grep -q .; then
    echo '发现其他已有站点；拒绝把旧卷当成全新系统初始化。' >&2
    exit 1
  fi
  [[ -n "$DB_ROOT_PASSWORD" && -n "$ADMIN_PASSWORD" ]] || { echo '初始化密码不能为空。' >&2; exit 1; }
  fresh_site=1
fi

run_bench() {
  sudo -H -u frappe /home/frappe/.local/bin/bench "$@"
}

install -d -o mysql -g mysql /run/mysqld /var/lib/mysql
install -d -o redis -g redis /var/lib/redis
install -d -o frappe -g frappe "$BENCH_DIR/sites" "$BENCH_DIR/logs"
install -d -o www-data -g adm -m 0750 "$BENCH_DIR/logs/nginx"

# 空 bind mount 不会像 Docker volume 一样复制镜像中的 sites 文件。
# 在首次 Bench 调用前生成公共 App 清单；已有站点配置及业务文件不覆盖。
apps_txt_tmp="$BENCH_DIR/sites/apps.txt.tmp"
jq -r '.[]' "$BENCH_DIR/apps-available.json" >"$apps_txt_tmp"
chown frappe:frappe "$apps_txt_tmp"
mv -f "$apps_txt_tmp" "$BENCH_DIR/sites/apps.txt"
if [[ ! -f "$BENCH_DIR/sites/common_site_config.json" ]]; then
  printf '{}\n' >"$BENCH_DIR/sites/common_site_config.json"
  chown frappe:frappe "$BENCH_DIR/sites/common_site_config.json"
fi

# 旧 sites 卷会遮蔽新镜像的 assets.json，导致页面引用已不存在的旧 CSS/JS。
# 仅同步镜像公共构建产物；不修改站点配置、附件或数据库。
install -d -o frappe -g frappe "$BENCH_DIR/sites/assets"
cp -a --remove-destination /opt/erpnext-assets/. "$BENCH_DIR/sites/assets/"

if [[ ! -d /var/lib/mysql/mysql ]]; then
  [[ "$fresh_site" == 1 ]] || { echo '现有站点缺少数据库；拒绝创建空数据库。' >&2; exit 1; }
  fresh_database=1
  mariadb-install-db \
    --user=mysql \
    --datadir=/var/lib/mysql \
    --auth-root-authentication-method=normal \
    --skip-test-db >/dev/null
fi

mariadbd --user=mysql --datadir=/var/lib/mysql --bind-address=127.0.0.1 &
db_pid=$!
redis-server /etc/redis/erpnext.conf --daemonize yes

# 迁移失败或收到停止信号时，先正常停止初始化阶段的服务。
cleanup_bootstrap() {
  redis-cli shutdown >/dev/null 2>&1 || true
  kill -TERM "$db_pid" >/dev/null 2>&1 || true
  wait "$db_pid" || true
}
trap cleanup_bootstrap EXIT
trap 'exit 143' TERM INT

db_ready=0
for _ in {1..90}; do
  if [[ -S /run/mysqld/mysqld.sock ]] && { [[ "$fresh_site" != 1 ]] || mariadb-admin --protocol=socket ping --silent >/dev/null 2>&1; }; then
    db_ready=1
    break
  fi
  sleep 1
done
[[ "$db_ready" == 1 ]] || { echo "MariaDB 启动超时" >&2; exit 1; }
redis_ready=0
for _ in {1..120}; do
  if [[ "$(redis-cli PING 2>/dev/null || true)" == PONG ]]; then redis_ready=1; break; fi
  sleep 1
done
[[ "$redis_ready" == 1 ]] || { echo "Redis 启动超时" >&2; exit 1; }

if [[ "$fresh_site" == 1 ]]; then
  # 基础镜像可能包含 MariaDB 系统表，必须确认没有任何应用库，不能仅检查 mysql 目录。
  existing_databases="$(mariadb --protocol=socket -uroot --batch --skip-column-names \
    -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME NOT IN ('mysql','information_schema','performance_schema','sys','test')")" || {
      echo '无法确认新站点数据库为空，拒绝初始化。' >&2; exit 1;
    }
  [[ -z "$existing_databases" ]] || { echo '数据库已存在但站点配置缺失；拒绝初始化，先检查恢复资料。' >&2; exit 1; }
  escaped_password=${DB_ROOT_PASSWORD//\\/\\\\}
  escaped_password=${escaped_password//\'/\'\'}
  mariadb --protocol=socket -uroot <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '${escaped_password}';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '${escaped_password}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL
fi

cd "$BENCH_DIR"
run_bench set-config -g redis_cache redis://127.0.0.1:6379
run_bench set-config -g redis_queue redis://127.0.0.1:6379
run_bench set-config -g redis_socketio redis://127.0.0.1:6379
run_bench set-config -g socketio_port 9000

if [[ ! -f "sites/${SITE_NAME}/site_config.json" ]]; then
  run_bench new-site "$SITE_NAME" \
    --db-host 127.0.0.1 \
    --db-root-username root \
    --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" \
    --no-mariadb-socket
fi

run_bench use "$SITE_NAME"
stamp="$BENCH_DIR/sites/$SITE_NAME/.optimized-runtime.json"
if [[ "$fresh_site" == 1 ]] || { [[ "${RUN_MIGRATIONS:-0}" == 1 ]] && ! cmp --silent /opt/erpnext-runtime/manifest.json "$stamp"; }; then
  sudo -H -u frappe env SITE_NAME="$SITE_NAME" "$BENCH_DIR/env/bin/python" /opt/erpnext-runtime/maintenance.py ready
  sudo -H -u frappe env SITE_NAME="$SITE_NAME" "$BENCH_DIR/env/bin/python" /opt/erpnext-runtime/maintenance.py check-upgrade
  if [[ "$fresh_site" != 1 ]]; then
    sudo -H -u frappe env SITE_NAME="$SITE_NAME" "$BENCH_DIR/env/bin/python" /opt/erpnext-runtime/maintenance.py backup
  fi
  installed_apps="$(run_bench --site "$SITE_NAME" list-apps --format json | jq -r '.[] | .[]')"
  while IFS= read -r app; do
    if ! grep -Fxq "$app" <<<"$installed_apps"; then
      run_bench --site "$SITE_NAME" install-app "$app"
      installed_apps+=$'\n'"$app"
    fi
  done < <(jq -r '.[]' "$BENCH_DIR/apps-install.json")
  run_bench --site "$SITE_NAME" migrate
  cp /opt/erpnext-runtime/manifest.json "$stamp.tmp"
  chown frappe:frappe "$stamp.tmp"
  mv "$stamp.tmp" "$stamp"
elif ! cmp --silent /opt/erpnext-runtime/manifest.json "$stamp"; then
  echo '镜像版本与站点标记不一致；请备份后显式 RUN_MIGRATIONS=1 执行升级。' >&2
  exit 1
else
  echo '版本一致：跳过应用安装与数据库迁移。'
fi

# 所有已安装应用、hooks及可选部署标记就绪后，才放行Web和后台worker。
sudo -E -H -u frappe env SITE_NAME="$SITE_NAME" "$BENCH_DIR/env/bin/python" /opt/erpnext-runtime/readiness.py imports

cleanup_bootstrap
trap - EXIT TERM INT

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf

