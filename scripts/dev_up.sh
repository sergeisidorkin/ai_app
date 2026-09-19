#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT/.venv/bin"

if [ ! -x "$VENV_BIN/python" ]; then
  echo "[dev_up] ERROR: не найден $VENV_BIN/python (создай venv: python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt)"
  exit 1
fi

export PATH="$VENV_BIN:$PATH"

echo "[dev_up] preflight: shutting down leftovers"
for p in 6380 8001 8000 3000 3080; do
  pids="$(lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
  fi
done

echo "[dev_up] preflight: ensuring local PostgreSQL"
"$ROOT/scripts/dev_postgres_preflight.sh"

echo "[dev_up] preflight: applying Django migrations"
"$VENV_BIN/python" "$ROOT/manage.py" migrate --noinput

echo "[dev_up] starting honcho"
exec "$VENV_BIN/python" -m honcho -e "$ROOT/.env.dev" -f "$ROOT/Procfile.dev" start
