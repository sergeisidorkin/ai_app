#!/usr/bin/env bash
set -Eeuo pipefail

: "${CLOUDPUB_PUBLIC_URL:=}"          # напр.: https://adamantly-fluttering-worm.cloudpub.ru
: "${CLOUDPUB_TARGET:=http://localhost:8000}"

echo "[cloudpub] using macOS GUI tunnel (no CLI here)"
echo "[cloudpub] local target: ${CLOUDPUB_TARGET}"
[[ -n "${CLOUDPUB_PUBLIC_URL}" ]] && echo "[cloudpub] public url : ${CLOUDPUB_PUBLIC_URL}" || \
  echo "[cloudpub] WARN: CLOUDPUB_PUBLIC_URL is empty (set it in .env.dev)"

check_once() {
  local ok=0
  if curl -fsS "${CLOUDPUB_TARGET}/health/" >/dev/null 2>&1; then
    echo "[cloudpub] local /health OK"
    ok=1
  else
    echo "[cloudpub] WARN: local /health not responding"
  fi

  if [[ -n "${CLOUDPUB_PUBLIC_URL}" ]]; then
    if curl -fsS "${CLOUDPUB_PUBLIC_URL}/health/" >/dev/null 2>&1; then
      echo "[cloudpub] public /health OK"
    else
      echo "[cloudpub] WARN: public /health not reachable (yet?)"
    fi
  fi
  return $ok
}

# keep honcho alive; periodic status
while :; do
  check_once || true
  sleep 10
done