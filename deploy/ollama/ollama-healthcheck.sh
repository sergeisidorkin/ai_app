#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/ollama}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/ollama.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-180}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

if [[ ! -f "$ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "ollama-healthcheck: compose or env file is missing" >&2
  exit 1
fi

env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
import sys
from pathlib import Path

for raw_line in Path(sys.argv[1]).read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() == sys.argv[2]:
        print(value.strip())
        break
PY
}

port="$(env_value OLLAMA_LOCAL_PORT)"
port="${port:-11434}"

deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${port}/api/tags" >/dev/null 2>&1; then
    echo "ollama-healthcheck: ok"
    exit 0
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

echo "ollama-healthcheck: API did not become ready on 127.0.0.1:${port}" >&2
compose ps || true
exit 1
