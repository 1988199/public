#!/usr/bin/env bash
set -Eeuo pipefail

export TZ="${ESPOCRM_TIME_ZONE:-Asia/Shanghai}"

: "${ESPOCRM_ADMIN_PASSWORD:?必须设置 ESPOCRM_ADMIN_PASSWORD}"
: "${ESPOCRM_DATABASE_PASSWORD:?必须设置 ESPOCRM_DATABASE_PASSWORD}"
: "${MARIADB_ROOT_PASSWORD:?必须设置 MARIADB_ROOT_PASSWORD}"
: "${ESPOCRM_SITE_URL:?必须设置 ESPOCRM_SITE_URL}"

DB_NAME="${ESPOCRM_DATABASE_NAME:-espocrm}"
DB_USER="${ESPOCRM_DATABASE_USER:-espocrm}"

mkdir -p /data/mysql /data/espocrm/data /data/espocrm/custom /data/espocrm/client-custom /run/mysqld
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
  mariadb-install-db --user=mysql --datadir=/data/mysql --auth-root-authentication-method=normal >/dev/null
fi

/usr/sbin/mariadbd   --user=mysql   --datadir=/data/mysql   --socket=/run/mysqld/mysqld.sock   --pid-file=/run/mysqld/mysqld-temp.pid   --bind-address=127.0.0.1   >/tmp/mariadb-init.log 2>&1 &
DB_PID=$!

for i in $(seq 1 60); do
  mariadb-admin --protocol=socket --socket=/run/mysqld/mysqld.sock ping --silent >/dev/null 2>&1 && break
  sleep 1
done

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

if [ "$(su -s /bin/bash www-data -c 'bin/command config:get isInstalled 2>/dev/null || true')" != "true" ]; then
  su -s /bin/bash www-data -c "bin/command config:populate"
  su -s /bin/bash www-data -c "bin/command config:set database.platform Mysql"
  su -s /bin/bash www-data -c "bin/command config:set database.host 127.0.0.1"
  su -s /bin/bash www-data -c "bin/command config:set database.port 3306"
  su -s /bin/bash www-data -c "bin/command config:set database.dbname '${DB_NAME}'"
  su -s /bin/bash www-data -c "bin/command config:set database.user '${DB_USER}'"
  su -s /bin/bash www-data -c "bin/command config:set database.password '${ESPOCRM_DATABASE_PASSWORD}'"
  su -s /bin/bash www-data -c "bin/command rebuild"
  su -s /bin/bash www-data -c "bin/command create-admin-user '${ESPOCRM_ADMIN_USERNAME:-admin}'" || true
  printf '%s\n' "${ESPOCRM_ADMIN_PASSWORD}" | su -s /bin/bash www-data -c "bin/command set-password '${ESPOCRM_ADMIN_USERNAME:-admin}'"
  su -s /bin/bash www-data -c "bin/command config:set language '${ESPOCRM_LANGUAGE:-zh_CN}'"
  su -s /bin/bash www-data -c "bin/command config:set siteUrl '${ESPOCRM_SITE_URL}'"
  su -s /bin/bash www-data -c "bin/command config:set dateFormat '${ESPOCRM_DATE_FORMAT:-YYYY-MM-DD}'"
  su -s /bin/bash www-data -c "bin/command config:set timeFormat '${ESPOCRM_TIME_FORMAT:-HH:mm}'"
  su -s /bin/bash www-data -c "bin/command config:set timeZone '${ESPOCRM_TIME_ZONE:-Asia/Shanghai}'"
  su -s /bin/bash www-data -c "bin/command config:set defaultCurrency '${ESPOCRM_DEFAULT_CURRENCY:-CNY}'"
  su -s /bin/bash www-data -c "bin/command populate-scheduled-jobs"
  su -s /bin/bash www-data -c "bin/command config:set jobRunInParallel false --type=bool"
  su -s /bin/bash www-data -c "bin/command config:set isInstalled true --type=bool"
else
  su -s /bin/bash www-data -c "bin/command clear-cache" || true
  su -s /bin/bash www-data -c "bin/command migrate"
fi

mariadb-admin --protocol=socket --socket=/run/mysqld/mysqld.sock -uroot -p"${MARIADB_ROOT_PASSWORD}" shutdown >/dev/null 2>&1 || kill "${DB_PID}" 2>/dev/null || true
wait "${DB_PID}" 2>/dev/null || true

exec "$@"
