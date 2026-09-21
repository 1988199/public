ARG ESPOCRM_VERSION=10.0.8
FROM espocrm/espocrm:${ESPOCRM_VERSION}

USER root

LABEL org.opencontainers.image.source="https://github.com/1988199/public"
LABEL org.opencontainers.image.description="EspoCRM Chinese single-container image optimized for 1C1G VPS"

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      mariadb-server mariadb-client supervisor tzdata procps ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /data/mysql /data/espocrm/data /data/espocrm/custom \
      /data/espocrm/client-custom /run/mysqld /var/log/supervisor; \
    chown -R mysql:mysql /data/mysql /run/mysqld; \
    chown -R www-data:www-data /data/espocrm

COPY config/mariadb.cnf /etc/mysql/mariadb.conf.d/90-espocrm-lowmem.cnf
COPY config/apache-mpm.conf /etc/apache2/mods-available/mpm_prefork.conf
COPY config/php-lowmem.ini /usr/local/etc/php/conf.d/99-lowmem.ini
COPY config/supervisord.conf /etc/supervisor/conf.d/espocrm.conf
COPY scripts/entrypoint-single.sh /usr/local/bin/entrypoint-single.sh

RUN chmod +x /usr/local/bin/entrypoint-single.sh

ENV ESPOCRM_DATABASE_PLATFORM=Mysql \
    ESPOCRM_DATABASE_HOST=127.0.0.1 \
    ESPOCRM_DATABASE_PORT=3306 \
    ESPOCRM_DATABASE_NAME=espocrm \
    ESPOCRM_DATABASE_USER=espocrm \
    ESPOCRM_LANGUAGE=zh_CN \
    ESPOCRM_TIME_ZONE=Asia/Shanghai \
    ESPOCRM_DATE_FORMAT=YYYY-MM-DD \
    ESPOCRM_TIME_FORMAT=HH:mm \
    ESPOCRM_DEFAULT_CURRENCY=CNY \
    ESPOCRM_ADMIN_USERNAME=admin

VOLUME ["/data"]
EXPOSE 80

ENTRYPOINT ["/usr/local/bin/entrypoint-single.sh"]
CMD ["/usr/bin/supervisord","-n","-c","/etc/supervisor/supervisord.conf"]
