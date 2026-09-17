#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/opt/ollama}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/ollama.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

model="$(
  python3 - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

wanted = "OLLAMA_MODEL"
for raw_line in Path(sys.argv[1]).read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() == wanted:
        print(value.strip())
        break
else:
    print("qwen3.5:9b")
PY
)"

echo "Pulling ${model} into the ollama container..."
compose exec ollama ollama pull "$model"
compose exec ollama ollama list
