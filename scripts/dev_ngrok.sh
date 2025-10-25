#!/usr/bin/env bash
set -Eeuo pipefail

: "${NGROK_BIN:=$(command -v ngrok || true)}"
: "${NGROK_TARGET:=http://localhost:8000}"
: "${NGROK_AUTHTOKEN:=}"
: "${NGROK_EXTRA_ARGS:=--pooling-enabled --log-format=logfmt}"

if [[ -z "${NGROK_BIN}" ]]; then
  echo "[ngrok] not found; keep process alive so honcho doesn't exit"
  while :; do sleep 3600; done
fi

echo "[ngrok] starting tunnel -> ${NGROK_TARGET}"
while :; do
  if [[ -n "${NGROK_AUTHTOKEN}" ]]; then
    "${NGROK_BIN}" http "${NGROK_TARGET}" --log=stdout --authtoken "${NGROK_AUTHTOKEN}" ${NGROK_EXTRA_ARGS} || true
  else
    "${NGROK_BIN}" http "${NGROK_TARGET}" --log=stdout ${NGROK_EXTRA_ARGS} || true
  fi
  echo "[ngrok] exited -> restart in 5s"
  sleep 5
done