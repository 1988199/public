ARG TWENTY_TAG=v2.41.0
FROM twentycrm/twenty:${TWENTY_TAG}

USER root
ARG TWENTY_TAG
LABEL org.opencontainers.image.source="https://github.com/1988199/public" \
      org.opencontainers.image.description="Twenty CRM with PostgreSQL 16, Redis and Supervisor in one container" \
      org.opencontainers.image.version="${TWENTY_TAG}"

RUN apk add --no-cache postgresql16 postgresql16-contrib redis supervisor su-exec \
    && test -x /app/entrypoint.sh \
    && test -f /app/packages/twenty-server/dist/main.js \
    && mkdir -p /data /run/twenty /run/postgresql \
    && rm -rf /app/packages/twenty-server/.local-storage \
    && ln -s /data/twenty /app/packages/twenty-server/.local-storage

COPY config/ /etc/twenty-single/
COPY scripts/ /usr/local/lib/twenty-single/
RUN chmod +x /usr/local/lib/twenty-single/*.sh

ENV NODE_ENV=production NODE_PORT=3000 STORAGE_TYPE=local \
    SERVER_URL=http://localhost:3000 PGDATA=/data/postgres \
    PATH="/usr/libexec/postgresql16:/usr/lib/postgresql16/bin:${PATH}"
WORKDIR /app/packages/twenty-server
VOLUME ["/data"]
EXPOSE 3000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=20s --timeout=10s --start-period=600s --retries=3 \
    CMD /usr/local/lib/twenty-single/healthcheck.sh
ENTRYPOINT ["/usr/local/lib/twenty-single/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/twenty-single/supervisord.conf"]
