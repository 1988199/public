ARG BENCH_IMAGE=frappe/bench:v5.31.0@sha256:6df74bce06ab017aa350a16ffdc7aff4559a4a1bf3d785d8e552dacc19b5f0e7
FROM ${BENCH_IMAGE}

ARG FRAPPE_REF=v16.35.0
ARG FRAPPE_REPO=https://github.com/frappe/frappe.git

# 仅供当前测试阶段使用；生产构建必须通过环境变量覆盖。
ENV DB_ROOT_PASSWORD=Pass1234 \
    ADMIN_PASSWORD=Pass1234

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        curl gettext-base jq mariadb-client mariadb-server nginx redis-server sudo supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/mysqld /var/lib/redis /var/log/supervisor \
    && chown -R mysql:mysql /run/mysqld /var/lib/mysql \
    && chown -R redis:redis /var/lib/redis \
    && rm -f /etc/nginx/sites-enabled/default

USER frappe
WORKDIR /home/frappe
RUN --mount=type=cache,id=myerp-yarn,target=/home/frappe/.cache/yarn,uid=1000,gid=1000 \
    --mount=type=cache,id=myerp-uv,target=/home/frappe/.cache/uv,uid=1000,gid=1000 \
    --mount=type=cache,id=myerp-pip,target=/home/frappe/.cache/pip,uid=1000,gid=1000 \
    bench init \
      --frappe-branch "${FRAPPE_REF}" \
      --frappe-path "${FRAPPE_REPO}" \
      --skip-redis-config-generation \
      frappe-bench

COPY --chown=frappe:frappe docker/apps.json /tmp/apps.json
COPY --chown=frappe:frappe docker/translations.json /tmp/translations.json
COPY --chown=frappe:frappe docker/install_apps.py /usr/local/lib/erpnext/install_apps.py
COPY --chown=frappe:frappe docker/install_translations.py /usr/local/lib/erpnext/install_translations.py
COPY --chown=frappe:frappe apps/china_sme_accounting /opt/erpnext-apps/china_sme_accounting
WORKDIR /home/frappe/frappe-bench
RUN bench set-redis-cache-host redis://127.0.0.1:6379 \
    && bench set-redis-queue-host redis://127.0.0.1:6379 \
    && bench set-redis-socketio-host redis://127.0.0.1:6379
RUN --mount=type=secret,id=extra_apps,required=false,uid=1000 \
    --mount=type=cache,id=myerp-yarn,target=/home/frappe/.cache/yarn,uid=1000,gid=1000 \
    --mount=type=cache,id=myerp-uv,target=/home/frappe/.cache/uv,uid=1000,gid=1000 \
    --mount=type=cache,id=myerp-pip,target=/home/frappe/.cache/pip,uid=1000,gid=1000 \
    redis-server --daemonize yes --dir /tmp --pidfile /tmp/redis.pid \
    && python /usr/local/lib/erpnext/install_apps.py \
      --manifest /tmp/apps.json \
      --optional-manifest /run/secrets/extra_apps \
      --local-app /opt/erpnext-apps/china_sme_accounting \
      --install-list /home/frappe/frappe-bench/apps-install.json \
      --available-list /home/frappe/frappe-bench/apps-available.json \
    && /home/frappe/frappe-bench/env/bin/python /usr/local/lib/erpnext/install_translations.py \
      --manifest /tmp/translations.json \
      --overrides /home/frappe/frappe-bench/apps/china_sme_accounting/china_sme_accounting/localization/zh_overrides.csv \
      --target /home/frappe/frappe-bench/apps/china_sme_accounting/china_sme_accounting/translations/zh.csv \
    && ln -s \
      /home/frappe/frappe-bench/apps/china_sme_accounting/china_sme_accounting/standards/cn_sme_2011_v1/accounts.json \
      /home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/account/chart_of_accounts/verified/cn_small_enterprise_accounting_standard.json \
    && bench build --production \
    && redis-cli shutdown nosave \
    && rm -rf \
      /home/frappe/frappe-bench/apps/crm/node_modules \
      /home/frappe/frappe-bench/apps/erpnext/node_modules \
      /home/frappe/frappe-bench/apps/hrms/node_modules \
    && rm -f /tmp/apps.json /tmp/translations.json

USER root
# 将构建产物清单及公共静态资源保存在 sites 持久卷之外，供升级时同步。
RUN cp -a /home/frappe/frappe-bench/sites/assets /opt/erpnext-assets
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
COPY docker/healthcheck.sh /usr/local/bin/healthcheck
COPY docker/supervisord.conf /etc/supervisor/conf.d/erpnext.conf
COPY docker/nginx.conf /etc/nginx/nginx.conf.template
COPY docker/mariadb.cnf /etc/mysql/mariadb.conf.d/60-erpnext.cnf
COPY docker/redis.conf /etc/redis/erpnext.conf
RUN chmod 0755 /usr/local/bin/entrypoint /usr/local/bin/healthcheck \
    && node_version="$(cat /home/frappe/.nvm/alias/default)" \
    && ln -s "/home/frappe/.nvm/versions/node/${node_version}/bin/node" /usr/local/bin/node

EXPOSE 80
VOLUME ["/var/lib/mysql", "/var/lib/redis", "/home/frappe/frappe-bench/sites", "/home/frappe/frappe-bench/logs"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
  CMD ["/usr/local/bin/healthcheck"]
ENTRYPOINT ["/usr/local/bin/entrypoint"]
