# syntax=docker/dockerfile:1
ARG BASE_IMAGE=ghcr.io/1988199/erpnext-single@sha256:5bf3984687b323649a5784a7b97705b99a18fe445721f3243386dfd3cae78043
FROM ${BASE_IMAGE} AS sqlite-build
USER root
ARG SQLITE_URL=https://www.sqlite.org/2026/sqlite-autoconf-3540000.tar.gz
ARG SQLITE_SHA3=f5e3e724e9c9b3b5d512c76b02082091a59eeea9becd169a9fbf4d376403acce
RUN apt-get update && apt-get install --no-install-recommends -y gcc libc6-dev curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl --fail --location --retry 3 "$SQLITE_URL" -o /tmp/sqlite.tar.gz \
    && /home/frappe/frappe-bench/env/bin/python -c \
       'import hashlib,sys; assert hashlib.sha3_256(open(sys.argv[1],"rb").read()).hexdigest()==sys.argv[2]' /tmp/sqlite.tar.gz "$SQLITE_SHA3" \
    && mkdir /tmp/sqlite-source /opt/sqlite-runtime \
    && tar -xzf /tmp/sqlite.tar.gz --strip-components=1 -C /tmp/sqlite-source \
    && gcc -O2 -fPIC -shared -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_RTREE \
       -DSQLITE_ENABLE_COLUMN_METADATA -DSQLITE_ENABLE_DBSTAT_VTAB -DSQLITE_ENABLE_UNLOCK_NOTIFY \
       /tmp/sqlite-source/sqlite3.c -Wl,-soname,libsqlite3.so.0 \
       -o /opt/sqlite-runtime/libsqlite3.so.0 -lpthread -ldl -lm

FROM ${BASE_IMAGE} AS runtime
USER root
ENV DB_ROOT_PASSWORD="" ADMIN_PASSWORD="" \
    LD_LIBRARY_PATH=/opt/sqlite-runtime \
    SITE_NAME=erp.localhost
COPY --from=sqlite-build /opt/sqlite-runtime /opt/sqlite-runtime
COPY docker/ /opt/erpnext-runtime/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
COPY docker/healthcheck.sh /usr/local/bin/healthcheck
COPY docker/supervisord.conf /etc/supervisor/conf.d/erpnext.conf
COPY docker/sqlite-runtime.conf /etc/ld.so.conf.d/00-erpnext-sqlite.conf
RUN chmod 0755 /usr/local/bin/entrypoint /usr/local/bin/healthcheck /opt/erpnext-runtime/wait-dependencies.sh \
    && ldconfig \
    && /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/test_sqlite.py

# 仅从官方固定提交升级 CRM 代码；不连接或迁移任何企业站点。
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN git -C apps/crm fetch --depth 1 origin 0d3910b456ef4fb913e77b29db011b3debc4f778 \
    && git -C apps/crm checkout --detach 0d3910b456ef4fb913e77b29db011b3debc4f778 \
    && env/bin/python -m pip install --no-deps -e apps/crm \
    && redis-server --daemonize yes --dir /tmp --pidfile /tmp/optimized-redis.pid \
    && bench build --app crm --production \
    && redis-cli shutdown nosave
USER root
RUN cp -a --remove-destination /home/frappe/frappe-bench/sites/assets/. /opt/erpnext-assets/ \
    && /home/frappe/frappe-bench/env/bin/python /opt/erpnext-runtime/test_sqlite.py
LABEL org.opencontainers.image.title="ERPNext V16 optimized runtime" \
      org.opencontainers.image.description="Pinned applications, compatible SQLite, explicit migration, safe startup and split queues"
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=15s --timeout=10s --start-period=240s --retries=6 CMD ["/usr/local/bin/healthcheck"]
ENTRYPOINT ["/usr/local/bin/entrypoint"]
