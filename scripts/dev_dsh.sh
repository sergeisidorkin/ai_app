#!/usr/bin/env bash
set -Eeuo pipefail

# Native laptop sidecar for honcho. Do not use `npx @deepseek-ai/dsh web`:
# npm exec looks up the `dsh` bin on PATH and exits 127 when the npx cache
# is incomplete or ~/.npm is not writable (root-owned entries).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DSH_DATA_DIR:-$ROOT/deploy/dsh/data}"
HOME_DIR="$DATA_DIR/home"
WORKSPACE_DIR="$DATA_DIR/workspace"
SKILLS_DIR="$DATA_DIR/skills"
NPM_PREFIX="$DATA_DIR/npm"
LAUNCH_FILE="$DATA_DIR/web-launch.url"
LOG_FILE="$DATA_DIR/web.log"
HOST="${DSH_HOST:-127.0.0.1}"
PORT="${DSH_LOCAL_PORT:-3080}"
VERSION="${DSH_VERSION:-0.1.5-rc.1}"
DSH_BIN="$NPM_PREFIX/node_modules/.bin/dsh"

mkdir -p "$HOME_DIR" "$WORKSPACE_DIR" "$SKILLS_DIR"

REPO_SKILLS="$ROOT/deploy/dsh/skills"
if [[ -d "$REPO_SKILLS" ]]; then
  mkdir -p "$HOME_DIR/skills"
  cp -R "$REPO_SKILLS/." "$HOME_DIR/skills/"
  cp -R "$REPO_SKILLS/." "$SKILLS_DIR/"
fi

fail_soft() {
  echo "[dsh] ERROR: $*" >&2
  if [[ -s "$LOG_FILE" ]]; then
    echo "[dsh] last log lines ($LOG_FILE):" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
  fi
  echo "[dsh] leaving process idle so honcho does not stop the rest of the stack" >&2
  trap 'exit 0' INT TERM
  while true; do sleep 3600; done
}

dsh_http_code() {
  curl -sS -o /dev/null -m 2 -w '%{http_code}' "http://${HOST}:${PORT}/" 2>/dev/null || echo "000"
}

write_plain_launch_url() {
  printf 'http://%s:%s\n' "$HOST" "$PORT" > "$LAUNCH_FILE"
}

apply_web_brand() {
  if [[ ! -x "$ROOT/deploy/dsh/apply-brand.sh" ]]; then
    return 0
  fi
  if ! "$ROOT/deploy/dsh/apply-brand.sh"; then
    echo "[dsh] warning: web branding was not applied" >&2
    return 1
  fi
}

if [[ "$(dsh_http_code)" =~ ^(200|401|302|403)$ ]]; then
  echo "[dsh] already listening on http://${HOST}:${PORT}"
  if [[ ! -s "$LAUNCH_FILE" ]]; then
    write_plain_launch_url
  fi
  if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
    # shellcheck disable=SC1091
    . "${HOME}/.nvm/nvm.sh"
    nvm use 22.20.0 >/dev/null 2>&1 || nvm use 22 >/dev/null 2>&1 || nvm use --lts >/dev/null 2>&1 || true
  fi
  export PATH="$(cd "$(dirname "$DSH_BIN")" && pwd):${PATH}"
  export DSH_HOME="$HOME_DIR"
  export DSH_BRANDING_DIR="$ROOT/deploy/dsh/branding"
  export DSH_BRAND_LOGO_SOURCE="$ROOT/core/static/core/icons/favicon.svg"
  apply_web_brand || true
  while true; do sleep 3600; done
fi

if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  . "${HOME}/.nvm/nvm.sh"
  nvm use 22.20.0 >/dev/null 2>&1 || nvm use 22 >/dev/null 2>&1 || nvm use --lts >/dev/null 2>&1 || true
fi

if ! command -v node >/dev/null 2>&1; then
  fail_soft "Node.js not found (need >= 20)"
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if (( node_major < 20 )); then
  fail_soft "Node $(node -v) is too old; DSH needs >= 20"
fi

export npm_config_cache="$DATA_DIR/cache/npm"
mkdir -p "$NPM_PREFIX" "$npm_config_cache"

need_install=0
if [[ ! -e "$DSH_BIN" ]]; then
  need_install=1
else
  installed="$("$DSH_BIN" -V 2>/dev/null || true)"
  if [[ "$installed" != "$VERSION" ]]; then
    need_install=1
  fi
fi

if [[ "$need_install" -eq 1 ]]; then
  echo "[dsh] installing @deepseek-ai/dsh@${VERSION}"
  if ! npm install --prefix "$NPM_PREFIX" --no-audit --no-fund --save-exact "@deepseek-ai/dsh@${VERSION}"; then
    fail_soft "npm install @deepseek-ai/dsh@${VERSION} failed"
  fi
fi

if [[ ! -e "$DSH_BIN" ]]; then
  fail_soft "dsh binary missing after install: $DSH_BIN"
fi

export PATH="$(cd "$(dirname "$DSH_BIN")" && pwd):${PATH}"
export DSH_HOME="$HOME_DIR"
export DSH_BRANDING_DIR="$ROOT/deploy/dsh/branding"
export DSH_BRAND_LOGO_SOURCE="$ROOT/core/static/core/icons/favicon.svg"

load_dsh_api_key() {
  local name="$1"
  local env_file="$ROOT/deploy/dsh/dsh.env"
  if [[ -n "${!name:-}" || ! -f "$env_file" ]]; then
    return 0
  fi
  local value
  value="$(grep -E "^${name}=" "$env_file" | tail -1 | cut -d= -f2- || true)"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  if [[ -n "$value" ]]; then
    export "${name}=${value}"
  fi
}

load_dsh_api_key OPENROUTER_API_KEY
load_dsh_api_key DEEPSEEK_API_KEY
load_dsh_api_key DASHSCOPE_API_KEY
load_dsh_api_key OLLAMA_API_KEY

if ! apply_web_brand; then
  fail_soft "web branding failed"
fi

cd "$WORKSPACE_DIR"
write_plain_launch_url

: > "$LOG_FILE"

echo "[dsh] starting DeepSeek Harness ${VERSION} on http://${HOST}:${PORT}"
"$DSH_BIN" web --no-open --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
pid=$!
stop_from_honcho=0
cleanup() {
  stop_from_honcho=1
  kill "$pid" 2>/dev/null || true
}
trap cleanup INT TERM
trap 'kill "$pid" 2>/dev/null || true' EXIT

ready=0
for _ in $(seq 1 180); do
  if grep -E 'dsh web: https?://' "$LOG_FILE" >/dev/null 2>&1; then
    python3 - "$LOG_FILE" "$LAUNCH_FILE" <<'PY'
import re
import sys

log_path, dest_path = sys.argv[1], sys.argv[2]
text = open(log_path, encoding="utf-8", errors="replace").read()
match = re.search(r"dsh web:\s+(\S+)", text)
if match:
    with open(dest_path, "w", encoding="utf-8") as handle:
        handle.write(match.group(1).strip() + "\n")
PY
    echo "[dsh] web UI ready at http://${HOST}:${PORT}/"
    ready=1
    break
  fi
  if [[ "$stop_from_honcho" -eq 1 ]]; then
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    fail_soft "process exited before the UI was ready"
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  fail_soft "timed out waiting for http://${HOST}:${PORT}/"
fi

wait "$pid"
status=$?
trap - EXIT INT TERM
if [[ "$stop_from_honcho" -eq 1 ]]; then
  exit 0
fi
if [[ "$status" -ne 0 ]]; then
  fail_soft "process exited with status ${status}"
fi
exit 0
