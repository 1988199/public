#!/bin/sh
set -eu
exec postgres -D /data/postgres -c listen_addresses=127.0.0.1 \
  -c unix_socket_directories=/run/postgresql -c shared_buffers=128MB -c max_connections=100
