#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT/.venv/bin"

if [ -f "$ROOT/.env.dev" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.env.dev"
fi

if [ -f "$ROOT/.env" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.env"
fi

DEV_POSTGRES_AUTO_RECOVER="${DEV_POSTGRES_AUTO_RECOVER:-1}"
DEV_POSTGRES_HOST="${DEV_POSTGRES_HOST:-}"
DEV_POSTGRES_PORT="${DEV_POSTGRES_PORT:-}"
DEV_POSTGRES_USER="${DEV_POSTGRES_USER:-}"
DEV_POSTGRES_SERVICE_LABEL="${DEV_POSTGRES_SERVICE_LABEL:-}"
DEV_POSTGRES_DATA_DIR="${DEV_POSTGRES_DATA_DIR:-}"
DEV_POSTGRES_ACTIVE_PID=""

log() {
  echo "[dev_postgres] $*"
}

extract_database_url_parts() {
  "$VENV_BIN/python" - <<'PY'
import os
from urllib.parse import urlparse

raw = os.environ.get("DATABASE_URL", "").strip()
if not raw:
    print("|||")
    raise SystemExit

parsed = urlparse(raw)
host = parsed.hostname or ""
port = parsed.port or ""
user = parsed.username or ""
print(f"{host}|{port}|{user}")
PY
}

ensure_runtime_defaults() {
  local parts host port user
  parts="$(extract_database_url_parts)"
  host="${parts%%|*}"
  parts="${parts#*|}"
  port="${parts%%|*}"
  user="${parts#*|}"

  DEV_POSTGRES_HOST="${DEV_POSTGRES_HOST:-$host}"
  DEV_POSTGRES_PORT="${DEV_POSTGRES_PORT:-${port:-5432}}"
  DEV_POSTGRES_USER="${DEV_POSTGRES_USER:-$user}"
}

is_local_database() {
  case "${DEV_POSTGRES_HOST:-}" in
    ""|"localhost"|"127.0.0.1"|"::1")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_ready() {
  "$VENV_BIN/python" - <<'PY' >/dev/null 2>&1
import os
import socket

host = os.environ.get("DEV_POSTGRES_HOST") or "127.0.0.1"
port = int(os.environ.get("DEV_POSTGRES_PORT") or "5432")

with socket.create_connection((host, port), timeout=1.5):
    pass
PY
}

resolve_service_label() {
  if [ -n "${DEV_POSTGRES_SERVICE_LABEL:-}" ]; then
    return 0
  fi

  local plist
  for plist in "$HOME"/Library/LaunchAgents/homebrew.mxcl.postgresql*.plist; do
    [ -e "$plist" ] || continue
    DEV_POSTGRES_SERVICE_LABEL="$(basename "$plist" .plist)"
    return 0
  done
  return 1
}

resolve_data_dir() {
  if [ -n "${DEV_POSTGRES_DATA_DIR:-}" ] && [ -d "${DEV_POSTGRES_DATA_DIR:-}" ]; then
    return 0
  fi

  if resolve_service_label; then
    local version_part candidate
    version_part="${DEV_POSTGRES_SERVICE_LABEL#homebrew.mxcl.}"
    candidate="/opt/homebrew/var/${version_part}"
    if [ -d "$candidate" ]; then
      DEV_POSTGRES_DATA_DIR="$candidate"
      return 0
    fi
  fi

  return 1
}

detect_active_postmaster() {
  resolve_data_dir || return 1

  local pid_file pid
  pid_file="${DEV_POSTGRES_DATA_DIR%/}/postmaster.pid"
  [ -f "$pid_file" ] || return 1

  pid="$(sed -n '1p' "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    DEV_POSTGRES_ACTIVE_PID="$pid"
    return 0
  fi
  return 1
}

clear_stale_postmaster_pid() {
  resolve_data_dir || return 0

  local pid_file pid status_line
  pid_file="${DEV_POSTGRES_DATA_DIR%/}/postmaster.pid"
  [ -f "$pid_file" ] || return 0

  pid="$(sed -n '1p' "$pid_file" 2>/dev/null || true)"
  status_line="$(sed -n '8p' "$pid_file" 2>/dev/null || true)"

  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    DEV_POSTGRES_ACTIVE_PID="$pid"
    log "detected active postmaster pid=$pid; stale lock cleanup skipped"
    return 0
  fi

  if [ -n "$status_line" ]; then
    log "removing stale postmaster.pid (state: ${status_line})"
  else
    log "removing stale postmaster.pid"
  fi
  rm -f "$pid_file"
}

start_service() {
  resolve_service_label || {
    log "launch agent label not configured; cannot auto-start PostgreSQL"
    return 1
  }

  local domain="gui/$(id -u)"
  local plist="$HOME/Library/LaunchAgents/${DEV_POSTGRES_SERVICE_LABEL}.plist"

  if ! launchctl print "${domain}/${DEV_POSTGRES_SERVICE_LABEL}" >/dev/null 2>&1; then
    if [ -f "$plist" ]; then
      log "bootstrapping launch agent ${DEV_POSTGRES_SERVICE_LABEL}"
      launchctl bootstrap "$domain" "$plist" >/dev/null 2>&1 || true
    fi
  fi

  log "kickstarting ${DEV_POSTGRES_SERVICE_LABEL}"
  launchctl kickstart -k "${domain}/${DEV_POSTGRES_SERVICE_LABEL}" >/dev/null 2>&1
}

wait_until_ready() {
  local attempt max_attempts
  max_attempts="${DEV_POSTGRES_WAIT_ATTEMPTS:-20}"
  for attempt in $(seq 1 "$max_attempts"); do
    if is_ready; then
      log "ready on ${DEV_POSTGRES_HOST:-127.0.0.1}:${DEV_POSTGRES_PORT:-5432}"
      return 0
    fi
    sleep 1
  done
  return 1
}

main() {
  ensure_runtime_defaults

  if ! is_local_database; then
    log "DATABASE_URL points to non-local host (${DEV_POSTGRES_HOST}); skipping auto-recovery"
    return 0
  fi

  if is_ready; then
    log "already ready on ${DEV_POSTGRES_HOST:-127.0.0.1}:${DEV_POSTGRES_PORT:-5432}"
    return 0
  fi

  if [ "$DEV_POSTGRES_AUTO_RECOVER" != "1" ]; then
    log "auto-recovery disabled; PostgreSQL is not reachable"
    return 1
  fi

  clear_stale_postmaster_pid
  if detect_active_postmaster; then
    log "postmaster pid=${DEV_POSTGRES_ACTIVE_PID} is running; waiting for readiness without restart"
  else
    start_service
  fi

  if wait_until_ready; then
    return 0
  fi

  log "PostgreSQL did not become ready"
  if resolve_data_dir; then
    log "data dir: ${DEV_POSTGRES_DATA_DIR}"
  fi
  if resolve_service_label; then
    log "launch agent: ${DEV_POSTGRES_SERVICE_LABEL}"
  fi
  return 1
}

main "$@"
