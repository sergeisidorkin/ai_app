#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[dsh] %s\n' "$*" >&2
}

fail() {
  log "error: $*"
  exit 1
}

DSH_HOME="${DSH_HOME:-/home/node/.dsh}"
DSH_WEB_PORT="${DSH_WEB_PORT:-3080}"
DSH_BRIDGE_PORT="${DSH_BRIDGE_PORT:-13080}"
DSH_PUBLIC_URL="${DSH_PUBLIC_URL:-}"
DSH_LAUNCH_URL_FILE="${DSH_LAUNCH_URL_FILE:-$DSH_HOME/web-launch.url}"
SETTINGS_TEMPLATE="${DSH_SETTINGS_TEMPLATE:-/usr/local/share/dsh/settings.yaml.example}"
SETTINGS_OLLAMA_TEMPLATE="${DSH_SETTINGS_OLLAMA_TEMPLATE:-/usr/local/share/dsh/settings.ollama.yaml.example}"

    mkdir -p \
      "$DSH_HOME" \
      "$DSH_HOME/skills" \
      "${NPM_CONFIG_CACHE:-$DSH_HOME/cache/npm}" \
      "${PNPM_HOME:-$DSH_HOME/pnpm}" \
      "${XDG_CACHE_HOME:-$DSH_HOME/cache}" \
      "${XDG_CONFIG_HOME:-$DSH_HOME/config}" \
      /workspace/sort-runs

if [[ ! -f "$DSH_HOME/settings.yaml" ]]; then
  if [[ -n "${SILICONFLOW_API_KEY:-}" && -f "$SETTINGS_TEMPLATE" ]]; then
    cp "$SETTINGS_TEMPLATE" "$DSH_HOME/settings.yaml"
    log "seeded $DSH_HOME/settings.yaml for SiliconFlow (Qwen/Qwen3.5-27B)"
  elif [[ -n "${DSH_LLM_BASE_URL:-}" && -f "$SETTINGS_OLLAMA_TEMPLATE" ]]; then
    llm_base_url="$DSH_LLM_BASE_URL"
    llm_model="${DSH_LLM_MODEL:-qwen3.5:9b}"
    sed \
      -e "s|__LLM_BASE_URL__|${llm_base_url}|g" \
      -e "s|__LLM_MODEL__|${llm_model}|g" \
      "$SETTINGS_OLLAMA_TEMPLATE" > "$DSH_HOME/settings.yaml"
    log "seeded $DSH_HOME/settings.yaml for ${llm_model} at ${llm_base_url}"
  else
    log "no SILICONFLOW_API_KEY or DSH_LLM_BASE_URL; skip settings seed — add a provider in the Web UI"
  fi
fi

if (( $# == 0 )); then
  set -- web
elif [[ "$1" == dsh ]]; then
  shift
fi

dsh_args=("$@")
web_mode=false
if [[ "${1:-}" == web ]]; then
  web_mode=true
elif [[ "${1:-}" == --profile && "${2:-}" == web ]]; then
  web_mode=true
fi

if ! $web_mode; then
  exec dsh "${dsh_args[@]}"
fi

if [[ -x /usr/local/bin/dsh-apply-brand ]]; then
  /usr/local/bin/dsh-apply-brand
elif [[ -x /opt/dsh/apply-brand.sh ]]; then
  /opt/dsh/apply-brand.sh
fi

for argument in "${dsh_args[@]}"; do
  case "$argument" in
    --dump-config|--dump-default-config|-h|--help)
      exec dsh "${dsh_args[@]}"
      ;;
  esac
done

if [[ -n "${DSH_TRUSTED_HOSTS:-}" ]]; then
  IFS=',' read -r -a trusted_hosts <<<"${DSH_TRUSTED_HOSTS}"
  dsh_args+=(--trusted-host "${trusted_hosts[@]}")
fi

has_port=false
has_no_open=false
for argument in "${dsh_args[@]}"; do
  case "$argument" in
    --port|--port=*) has_port=true ;;
    --no-open) has_no_open=true ;;
  esac
done
if ! $has_port; then
  dsh_args+=(--port "$DSH_WEB_PORT")
fi
if ! $has_no_open; then
  dsh_args+=(--no-open)
fi

log "forwarding 0.0.0.0:${DSH_BRIDGE_PORT} -> 127.0.0.1:${DSH_WEB_PORT}"
socat \
  "TCP4-LISTEN:${DSH_BRIDGE_PORT},bind=0.0.0.0,reuseaddr,fork" \
  "TCP4:127.0.0.1:${DSH_WEB_PORT}" &
bridge_pid=$!

capture_dsh_output() {
  local target_fd="$1"
  local line query tmp
  while IFS= read -r line; do
    printf '%s\n' "$line" >&"$target_fd"
    if [[ -n "$DSH_PUBLIC_URL" && "$line" =~ dsh[[:space:]]web:[[:space:]]http://[^?[:space:]]+(\?token=[^[:space:]]+) ]]; then
      query="${BASH_REMATCH[1]}"
      tmp="${DSH_LAUNCH_URL_FILE}.tmp.$$"
      printf '%s/%s\n' "${DSH_PUBLIC_URL%/}" "$query" > "$tmp"
      chmod 0600 "$tmp"
      mv -f "$tmp" "$DSH_LAUNCH_URL_FILE"
      log "updated public DSH launch URL"
    fi
  done
}

dsh "${dsh_args[@]}" \
  > >(capture_dsh_output 1) \
  2> >(capture_dsh_output 2) &
dsh_pid=$!

stop_children() {
  kill -TERM "$dsh_pid" "$bridge_pid" 2>/dev/null || true
}

trap 'stop_children; wait "$dsh_pid" 2>/dev/null || true; wait "$bridge_pid" 2>/dev/null || true; exit 0' TERM INT

set +e
wait -n "$dsh_pid" "$bridge_pid"
status=$?
set -e
stop_children
wait "$dsh_pid" 2>/dev/null || true
wait "$bridge_pid" 2>/dev/null || true
exit "$status"
