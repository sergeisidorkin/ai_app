#!/bin/sh
# Starts SGLang only after a checkpoint path is configured.
# Quantization, context length, and KV cache stay in SGLANG_EXTRA_ARGS /
# SGLANG_CONTEXT_LENGTH and are filled on the weight step.
set -eu

if [ -z "${SGLANG_MODEL_PATH:-}" ]; then
  echo "sglang: SGLANG_MODEL_PATH is empty; choose a checkpoint before starting" >&2
  exit 1
fi

set -- python3 -m sglang.launch_server \
  --model-path "$SGLANG_MODEL_PATH" \
  --served-model-name "${SGLANG_SERVED_MODEL_NAME:-qwen3.8-27b-local}" \
  --host 0.0.0.0 \
  --port 30000 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder

if [ -n "${SGLANG_CONTEXT_LENGTH:-}" ]; then
  set -- "$@" --context-length "$SGLANG_CONTEXT_LENGTH"
fi

if [ -n "${SGLANG_API_KEY:-}" ]; then
  set -- "$@" --api-key "$SGLANG_API_KEY"
fi

if [ -n "${SGLANG_EXTRA_ARGS:-}" ]; then
  # Intentional split: flags are space-separated and contain no quoted spaces.
  # shellcheck disable=SC2086
  set -- "$@" $SGLANG_EXTRA_ARGS
fi

exec "$@"
