#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/moodle}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/moodle.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
HELPER_SYNC_SCRIPT="${HELPER_SYNC_SCRIPT:-$ROOT_DIR/moodle-sync-local-helper.sh}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "moodle-healthcheck: missing env file: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "moodle-healthcheck: missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
target = sys.argv[2]

for raw_line in env_path.read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == target:
        print(value.strip())
        break
PY
}

MOODLE_HOST="${MOODLE_HOST:-$(env_value MOODLE_HOST)}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://$MOODLE_HOST}"
FRONT_PAGE_URL="${FRONT_PAGE_URL:-$PUBLIC_BASE_URL/}"
OIDC_ENTRY_URL="${OIDC_ENTRY_URL:-$PUBLIC_BASE_URL/auth/oidc/}"
HELPER_ENTRY_URL="${HELPER_ENTRY_URL:-$PUBLIC_BASE_URL/local/imc_sso/logout_first.php?next=%2Fauth%2Foidc%2F%3Fsource%3Ddjango}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-180}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-5}"

wait_for_http_200() {
  local url="$1"
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --location --max-redirs 0 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done

  echo "moodle-healthcheck: timed out waiting for HTTP 200 from $url" >&2
  return 1
}

assert_oidc_redirect() {
  local headers
  headers="$(curl --silent --show-error --max-redirs 0 --dump-header - --output /dev/null "$OIDC_ENTRY_URL")"

  if ! HEADER_TEXT="$headers" python3 - <<'PY'
import os

headers = os.environ.get("HEADER_TEXT", "").splitlines()
status_line = next((line for line in headers if line.startswith("HTTP/")), "")
location_line = next((line for line in headers if line.lower().startswith("location:")), "")

if not status_line:
    raise SystemExit(1)

try:
    status_code = int(status_line.split()[1])
except Exception:
    raise SystemExit(1)

location_value = location_line.split(":", 1)[1].strip() if ":" in location_line else ""

if status_code not in {302, 303}:
    raise SystemExit(1)

if "/o/authorize/" not in location_value:
    raise SystemExit(1)
PY
  then
    echo "moodle-healthcheck: auth_oidc did not redirect to Django OIDC authorize endpoint" >&2
    printf '%s\n' "$headers" >&2
    return 1
  fi
}

assert_helper_redirect() {
  local headers
  headers="$(curl --silent --show-error --max-redirs 0 --dump-header - --output /dev/null "$HELPER_ENTRY_URL")"

  if ! HEADER_TEXT="$headers" python3 - <<'PY'
import os

headers = os.environ.get("HEADER_TEXT", "").splitlines()
status_line = next((line for line in headers if line.startswith("HTTP/")), "")
location_line = next((line for line in headers if line.lower().startswith("location:")), "")

if not status_line:
    raise SystemExit(1)

try:
    status_code = int(status_line.split()[1])
except Exception:
    raise SystemExit(1)

location_value = location_line.split(":", 1)[1].strip() if ":" in location_line else ""

if status_code not in {302, 303}:
    raise SystemExit(1)

if "/auth/oidc/" not in location_value:
    raise SystemExit(1)
PY
  then
    echo "moodle-healthcheck: local_imc_sso did not redirect into auth_oidc" >&2
    printf '%s\n' "$headers" >&2
    return 1
  fi
}

sync_local_helper() {
  if [[ -x "$HELPER_SYNC_SCRIPT" ]]; then
    "$HELPER_SYNC_SCRIPT"
  fi
}

assert_live_config_present() {
  local cid
  cid="$(compose ps -q moodle)"
  [[ -n "$cid" ]]
  docker exec "$cid" sh -lc 'test -f /var/www/moodle/config.php'
}

wait_for_helper_redirect() {
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    sync_local_helper
    if assert_helper_redirect; then
      return 0
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done

  echo "moodle-healthcheck: timed out waiting for local_imc_sso helper redirect" >&2
  return 1
}

echo "moodle-healthcheck: waiting for front page"
wait_for_http_200 "$FRONT_PAGE_URL"

echo "moodle-healthcheck: checking live Moodle config"
assert_live_config_present

echo "moodle-healthcheck: checking local_imc_sso helper redirect"
wait_for_helper_redirect

echo "moodle-healthcheck: checking auth_oidc redirect"
assert_oidc_redirect

echo "moodle-healthcheck: OK"
