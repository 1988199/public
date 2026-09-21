#!/usr/bin/env bash
set -Eeuo pipefail

export TZ="${ESPOCRM_TIME_ZONE:-Asia/Shanghai}"

CREDENTIAL_FILE="/data/.credentials"
FIRST_CREDENTIAL_INIT=false

generate_secret() {
  od -An -N18 -tx1 /dev/urandom | tr -d ' \n'
}

mkdir -p /data /data/mysql /data/espocrm/data /data/espocrm/custom /data/espocrm/client-custom /run/mysqld
chmod 700 /data

# 先读取首次启动时持久化的内部凭据。
# 用户显式传入的环境变量优先级更高。
if [ -f "${CREDENTIAL_FILE}" ]; then
  # shellcheck disable=SC1090
  source "${CREDENTIAL_FILE}"
fi

ESPOCRM_ADMIN_USERNAME="${ESPOCRM_ADMIN_USERNAME:-admin}"
ESPOCRM_SITE_URL="${ESPOCRM_SITE_URL:-http://localhost:8080}"

if [ -z "${ESPOCRM_ADMIN_PASSWORD:-}" ]; then
  ESPOCRM_ADMIN_PASSWORD="$(generate_secret)"
  FIRST_CREDENTIAL_INIT=true
fi

if [ -z "${ESPOCRM_DATABASE_PASSWORD:-}" ]; then
  ESPOCRM_DATABASE_PASSWORD="$(generate_secret)"
  FIRST_CREDENTIAL_INIT=true
fi

if [ -z "${MARIADB_ROOT_PASSWORD:-}" ]; then
  MARIADB_ROOT_PASSWORD="$(generate_secret)"
  FIRST_CREDENTIAL_INIT=true
fi

export ESPOCRM_ADMIN_USERNAME
export ESPOCRM_ADMIN_PASSWORD
export ESPOCRM_DATABASE_PASSWORD
export MARIADB_ROOT_PASSWORD
export ESPOCRM_SITE_URL

# 第一次生成后保存，后续容器重启/重建继续复用，不会随机改变。
if [ ! -f "${CREDENTIAL_FILE}" ] || [ "${FIRST_CREDENTIAL_INIT}" = "true" ]; then
  umask 077
  cat > "${CREDENTIAL_FILE}" <<EOF
ESPOCRM_ADMIN_PASSWORD='${ESPOCRM_ADMIN_PASSWORD}'
ESPOCRM_DATABASE_PASSWORD='${ESPOCRM_DATABASE_PASSWORD}'
MARIADB_ROOT_PASSWORD='${MARIADB_ROOT_PASSWORD}'
EOF
  chmod 600 "${CREDENTIAL_FILE}"
fi

DB_NAME="${ESPOCRM_DATABASE_NAME:-espocrm}"
DB_USER="${ESPOCRM_DATABASE_USER:-espocrm}"

chown -R mysql:mysql /data/mysql /run/mysqld
chown -R www-data:www-data /data/espocrm

for d in data custom; do
  if [ -e "/var/www/html/$d" ] && [ ! -L "/var/www/html/$d" ]; then
    if [ -z "$(ls -A "/data/espocrm/$d" 2>/dev/null || true)" ]; then
      cp -a "/var/www/html/$d/." "/data/espocrm/$d/" 2>/dev/null || true
    fi
    rm -rf "/var/www/html/$d"
  fi
  ln -sfn "/data/espocrm/$d" "/var/www/html/$d"
done

mkdir -p /var/www/html/client
if [ -e "/var/www/html/client/custom" ] && [ ! -L "/var/www/html/client/custom" ]; then
  if [ -z "$(ls -A /data/espocrm/client-custom 2>/dev/null || true)" ]; then
    cp -a /var/www/html/client/custom/. /data/espocrm/client-custom/ 2>/dev/null || true
  fi
  rm -rf /var/www/html/client/custom
fi
ln -sfn /data/espocrm/client-custom /var/www/html/client/custom
chown -R www-data:www-data /data/espocrm

if [ ! -d /data/mysql/mysql ]; then
  echo "[初始化] 创建 MariaDB 数据目录"
  mariadb-install-db --user=mysql --datadir=/data/mysql --auth-root-authentication-method=normal >/dev/null
fi

/usr/sbin/mariadbd \
  --user=mysql \
  --datadir=/data/mysql \
  --socket=/run/mysqld/mysqld.sock \
  --pid-file=/run/mysqld/mysqld-temp.pid \
  --bind-address=127.0.0.1 \
  >/tmp/mariadb-init.log 2>&1 &
DB_PID=$!

DB_READY=false
for i in $(seq 1 60); do
  if mariadb-admin --protocol=socket --socket=/run/mysqld/mysqld.sock ping --silent >/dev/null 2>&1; then
    DB_READY=true
    break
  fi
  sleep 1
done

if [ "${DB_READY}" != "true" ]; then
  echo "[错误] MariaDB 启动失败"
  cat /tmp/mariadb-init.log || true
  exit 1
fi

if mariadb --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot -e "SELECT 1" >/dev/null 2>&1; then
  mariadb --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED BY '${MARIADB_ROOT_PASSWORD}';
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
else
  mariadb --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot -p"${MARIADB_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${ESPOCRM_DATABASE_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
fi

cd /var/www/html

IS_INSTALLED="$(su -s /bin/bash www-data -c 'bin/command config:get isInstalled 2>/dev/null || true')"

if [ "${IS_INSTALLED}" != "true" ]; then
  echo "[安装] 初始化 EspoCRM（简体中文）"

  su -s /bin/bash www-data -c "bin/command config:populate"
  su -s /bin/bash www-data -c "bin/command config:set database.platform Mysql"
  su -s /bin/bash www-data -c "bin/command config:set database.host 127.0.0.1"
  su -s /bin/bash www-data -c "bin/command config:set database.port 3306"
  su -s /bin/bash www-data -c "bin/command config:set database.dbname '${DB_NAME}'"
  su -s /bin/bash www-data -c "bin/command config:set database.user '${DB_USER}'"
  su -s /bin/bash www-data -c "bin/command config:set database.password '${ESPOCRM_DATABASE_PASSWORD}'"

  su -s /bin/bash www-data -c "bin/command rebuild"
  su -s /bin/bash www-data -c "bin/command create-admin-user '${ESPOCRM_ADMIN_USERNAME}'" || true
  printf '%s\n' "${ESPOCRM_ADMIN_PASSWORD}" | su -s /bin/bash www-data -c "bin/command set-password '${ESPOCRM_ADMIN_USERNAME}'"

  su -s /bin/bash www-data -c "bin/command config:set language '${ESPOCRM_LANGUAGE:-zh_CN}'"
  su -s /bin/bash www-data -c "bin/command config:set siteUrl '${ESPOCRM_SITE_URL}'"
  su -s /bin/bash www-data -c "bin/command config:set dateFormat '${ESPOCRM_DATE_FORMAT:-YYYY-MM-DD}'"
  su -s /bin/bash www-data -c "bin/command config:set timeFormat '${ESPOCRM_TIME_FORMAT:-HH:mm}'"
  su -s /bin/bash www-data -c "bin/command config:set timeZone '${ESPOCRM_TIME_ZONE:-Asia/Shanghai}'"
  su -s /bin/bash www-data -c "bin/command config:set defaultCurrency '${ESPOCRM_DEFAULT_CURRENCY:-CNY}'"
  su -s /bin/bash www-data -c "bin/command populate-scheduled-jobs"
  su -s /bin/bash www-data -c "bin/command config:set jobRunInParallel false --type=bool"
  su -s /bin/bash www-data -c "bin/command config:set isInstalled true --type=bool"

  echo ""
  echo "============================================================"
  echo " EspoCRM 首次初始化完成"
  echo "------------------------------------------------------------"
  echo " 登录地址: ${ESPOCRM_SITE_URL}"
  echo " 管理员账号: ${ESPOCRM_ADMIN_USERNAME}"
  echo " 管理员密码: ${ESPOCRM_ADMIN_PASSWORD}"
  echo "------------------------------------------------------------"
  echo " 请立即保存管理员密码，并在首次登录后修改密码。"
  echo " 内部数据库凭据已保存在持久化文件: /data/.credentials"
  echo "============================================================"
  echo ""
else
  echo "[启动] 检测到已安装的 EspoCRM，不重新生成管理员密码"
  su -s /bin/bash www-data -c "bin/command clear-cache" || true
  su -s /bin/bash www-data -c "bin/command migrate"
fi

mariadb-admin --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot -p"${MARIADB_ROOT_PASSWORD}" shutdown >/dev/null 2>&1 || kill "${DB_PID}" 2>/dev/null || true
wait "${DB_PID}" 2>/dev/null || true

exec "$@"
