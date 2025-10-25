#!/usr/bin/env bash
set -Eeuo pipefail

# --- helpers ---
wait_http() {  # $1=url  $2=timeout_sec
  local url="${1}"; local t="${2:-60}"
  local curl_opts=(-fsS)
  [[ "$url" == https://* ]] && curl_opts=(-kfsS)      # <— важное отличие
  for i in $(seq 1 "$t"); do
    if curl "${curl_opts[@]}" "$url" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}

wait_tls() {  # $1=host:port  $2=timeout_sec
  local hp="${1}"; local t="${2:-60}"
  for i in $(seq 1 "$t"); do
    if openssl s_client -connect "$hp" -servername localhost -tls1_2 </dev/null 2>/dev/null | head -n 1 | grep -q 'CONNECTED'; then
      return 0
    fi
    sleep 1
  done
  return 1
}

hold_on_port() {  # $1=port
  local p="${1}"
  echo "[addin] holding while port :$p is LISTEN ..."
  while lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; do
    sleep 2
  done
}

APP_DIR="office_addin_client/IMC Montan Office Add-in"

cleanup() {
  echo "[addin] stopping Office Add-in debugging..."
  if [[ -d "$APP_DIR" ]]; then
    ( cd "$APP_DIR" && [[ -f manifest.local.xml ]] && npx --yes office-addin-debugging stop manifest.local.xml ) || true
  fi
  pkill -f "webpack serve --mode development" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# --- readiness ---
echo "[addin] waiting API http://localhost:8000/health/ ..."
wait_http "http://localhost:8000/health/" 60 && echo "[addin] API is up"

echo "[addin] waiting WSS https://localhost:8001 ..."
wait_tls "localhost:8001" 60 && echo "[addin] WSS is up"

# --- start add-in ---
echo "[addin] starting Office Add-in from: ${APP_DIR}"
cd "${APP_DIR}"

# nvm (если есть) + .nvmrc
if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then . "${HOME}/.nvm/nvm.sh"; fi
if [[ -f .nvmrc ]]; then nvm use >/dev/null; fi

# на всякий: остановим предыдущую сессию (мягко)
[[ -f manifest.local.xml ]] && npx --yes office-addin-debugging stop manifest.local.xml || true

# старт
npx --yes office-addin-debugging start manifest.local.xml

echo "[addin] waiting dev-server on https://localhost:3000 ..."
wait_http "https://localhost:3000/" 30 || wait_http "https://localhost:3000/taskpane.html" 30 || true

hold_on_port 3000