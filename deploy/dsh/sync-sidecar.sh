#!/usr/bin/env bash
set -euo pipefail

# Copy DSH compose artifacts from a repo checkout into an existing DSH_ROOT
# without touching secrets or session state. Prints SIDECAR_CHANGED=1 when
# the container should be rebuilt/recreated.

usage() {
  echo "usage: sync-sidecar.sh REPO_DIR DSH_ROOT" >&2
  exit 2
}

[[ "${1:-}" == -h || "${1:-}" == --help ]] && usage
[[ $# -eq 2 ]] || usage

REPO_DIR="$(cd "$1" && pwd)"
DSH_ROOT="$(cd "$2" && pwd)"
SRC="$REPO_DIR/deploy/dsh"

if [[ ! -f "$SRC/docker-compose.yml" ]]; then
  echo "SIDECAR_CHANGED=0"
  echo "repo deploy/dsh is missing" >&2
  exit 0
fi
if [[ ! -d "$DSH_ROOT" ]]; then
  echo "SIDECAR_CHANGED=0"
  echo "dsh sidecar is not installed; skip" >&2
  exit 0
fi

FILES=(
  Dockerfile
  docker-compose.yml
  docker-compose.ollama.yml
  docker-entrypoint.sh
  apply-brand.sh
  sync-sidecar.sh
  container-healthcheck.sh
  dsh-healthcheck.sh
  settings.yaml.example
  settings.ollama.yaml.example
  branding/brand.yaml
  branding/logo.svg
  plugins/imc-brand/package.json
  plugins/imc-brand/cordis.patch.yml
  plugins/imc-brand/index.js
  plugins/imc-brand/client.js
)

FAVICON="$REPO_DIR/core/static/core/icons/favicon.svg"

desired="$(
  python3 - "$SRC" "$FAVICON" "${FILES[@]}" <<'PY'
from pathlib import Path
import hashlib
import sys

root = Path(sys.argv[1])
favicon = Path(sys.argv[2])
h = hashlib.sha256()
for rel in sys.argv[3:]:
    path = root / rel
    h.update(rel.encode())
    h.update(b"\0")
    if rel == "branding/logo.svg" and favicon.is_file():
        h.update(favicon.read_bytes())
    elif path.is_file():
        h.update(path.read_bytes())
    h.update(b"\0")
print(h.hexdigest())
PY
)"

for rel in "${FILES[@]}"; do
  [[ -f "$SRC/$rel" ]] || continue
  mkdir -p "$(dirname "$DSH_ROOT/$rel")"
  cp "$SRC/$rel" "$DSH_ROOT/$rel"
done
chmod 0755 "$DSH_ROOT/apply-brand.sh" "$DSH_ROOT/sync-sidecar.sh" \
  "$DSH_ROOT/docker-entrypoint.sh" "$DSH_ROOT/container-healthcheck.sh" \
  "$DSH_ROOT/dsh-healthcheck.sh" 2>/dev/null || true

if [[ -f "$FAVICON" ]]; then
  mkdir -p "$DSH_ROOT/branding"
  cp "$FAVICON" "$DSH_ROOT/branding/logo.svg"
fi

if [[ -d "$SRC/skills" ]]; then
  mkdir -p "$DSH_ROOT/skills"
  cp -R "$SRC/skills/." "$DSH_ROOT/skills/"
fi

stamp_file="$DSH_ROOT/.ai-app-sidecar.sha256"
previous=""
[[ -f "$stamp_file" ]] && previous="$(tr -d '[:space:]' < "$stamp_file")"
printf '%s\n' "$desired" > "$stamp_file"

if [[ "$desired" != "$previous" ]]; then
  echo "SIDECAR_CHANGED=1"
else
  echo "SIDECAR_CHANGED=0"
fi
