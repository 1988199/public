#!/usr/bin/env bash
set -Eeuo pipefail

BENCH_DIR=/home/frappe/frappe-bench
SITE_NAME="${SITE_NAME:-erp.localhost}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-Pass1234}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Pass1234}"
export SITE_NAME

if [[ ! "$SITE_NAME" =~ ^[a-z0-9][a-z0-9.-]*$ ]]; then
  echo "SITE_NAME 只能包含小写字母、数字、点和连字符。" >&2
  exit 1
fi

# 浏览器使用 localhost，内部仍可沿用持久卷中既有的站点名。
envsubst '${SITE_NAME}' </etc/nginx/nginx.conf.template >/etc/nginx/nginx.conf
nginx -t

if [[ "${DB_ROOT_PASSWORD}" == "Pass1234" || "${ADMIN_PASSWORD}" == "Pass1234" ]]; then
  echo "警告：正在使用测试密码 Pass1234，禁止用于正式环境。" >&2
fi

run_bench() {
  sudo -H -u frappe /home/frappe/.local/bin/bench "$@"
}

install -d -o mysql -g mysql /run/mysqld /var/lib/mysql
install -d -o redis -g redis /var/lib/redis
install -d -o frappe -g frappe "$BENCH_DIR/sites" "$BENCH_DIR/logs"

# 旧 sites 卷会遮蔽新镜像的 assets.json，导致页面引用已不存在的旧 CSS/JS。
# 仅同步镜像公共构建产物；不修改站点配置、附件或数据库。
install -d -o frappe -g frappe "$BENCH_DIR/sites/assets"
cp -a --remove-destination /opt/erpnext-assets/. "$BENCH_DIR/sites/assets/"

if [[ ! -d /var/lib/mysql/mysql ]]; then
  mariadb-install-db \
    --user=mysql \
    --datadir=/var/lib/mysql \
    --auth-root-authentication-method=normal \
    --skip-test-db >/dev/null
fi

mariadbd --user=mysql --datadir=/var/lib/mysql --bind-address=127.0.0.1 &
db_pid=$!
redis-server /etc/redis/erpnext.conf --daemonize yes

for _ in {1..60}; do
  mariadb-admin ping --silent && break
  sleep 1
done
mariadb-admin ping --silent || { echo "MariaDB 启动超时" >&2; exit 1; }

if mariadb --protocol=socket -uroot -e 'SELECT 1' >/dev/null 2>&1; then
  escaped_password=${DB_ROOT_PASSWORD//\'/\'\'}
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

apps_txt_tmp="$BENCH_DIR/sites/apps.txt.tmp"
jq -r '.[]' "$BENCH_DIR/apps-available.json" >"$apps_txt_tmp"
chown frappe:frappe "$apps_txt_tmp"
mv -f "$apps_txt_tmp" "$BENCH_DIR/sites/apps.txt"

if [[ ! -f "sites/${SITE_NAME}/site_config.json" ]]; then
  run_bench new-site "$SITE_NAME" \
    --db-host 127.0.0.1 \
    --db-root-username root \
    --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" \
    --no-mariadb-socket
fi

installed_apps="$(run_bench --site "$SITE_NAME" list-apps --format json | jq -r '.[] | .[]')"
while IFS= read -r app; do
  if ! grep -Fxq "$app" <<<"$installed_apps"; then
    run_bench --site "$SITE_NAME" install-app "$app"
    installed_apps+=$'\n'"$app"
  fi
done < <(jq -r '.[]' "$BENCH_DIR/apps-install.json")

run_bench use "$SITE_NAME"
run_bench --site "$SITE_NAME" migrate

redis-cli shutdown nosave || true
kill "$db_pid"
wait "$db_pid" || true

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
