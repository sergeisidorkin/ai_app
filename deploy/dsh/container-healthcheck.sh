#!/usr/bin/env sh
set -eu
port="${DSH_WEB_PORT:-3080}"
# DSH protects the root page with its launch token. An unauthenticated 401
# still proves that the HTTP server and bridge are ready.
curl --silent --show-error --max-time 3 "http://127.0.0.1:${port}/" >/dev/null
