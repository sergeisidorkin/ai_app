#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/nextcloud}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/nextcloud.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-180}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

if [[ ! -f "$ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "nextcloud-healthcheck: compose or env file is missing" >&2
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
    key, value = line.split("=", 1)
    if key.strip() == sys.argv[2]:
        print(value.strip())
        break
PY
}

deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  cid="$(compose ps -q nextcloud)"
  health="$(
    if [[ -n "$cid" ]]; then
      docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid"
    fi
  )"
  if [[ "$health" == "healthy" ]]; then
    break
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

if [[ "${health:-}" != "healthy" ]]; then
  echo "nextcloud-healthcheck: Nextcloud container did not become healthy" >&2
  compose ps >&2
  exit 1
fi

compose exec -T nextcloud php occ status --output=json \
  | python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("installed") else 1)'

local_port="$(env_value NEXTCLOUD_LOCAL_PORT)"
nextcloud_host="$(env_value NEXTCLOUD_HOST)"
curl --fail --silent --show-error --max-time 10 \
  -H "Host: ${nextcloud_host}" \
  "http://127.0.0.1:${local_port:-8091}/status.php" >/dev/null

echo "nextcloud-healthcheck: OK"
