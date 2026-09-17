#!/usr/bin/env bash
set -euo pipefail

# Idempotent DSH web branding. Installs the in-repo slot plugin into the web
# profile, disables the DeepSeek wordmark, and points the mark at the IMC logo.
# Safe to run on every web start; does not touch the headless profile.

log() {
  printf '[dsh-brand] %s\n' "$*" >&2
}

fail() {
  log "error: $*"
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DSH_HOME="${DSH_HOME:-}"
[[ -n "$DSH_HOME" ]] || fail "DSH_HOME is not set"

BRANDING_DIR="${DSH_BRANDING_DIR:-}"
if [[ -z "$BRANDING_DIR" ]]; then
  if [[ -d /usr/local/share/dsh/branding ]]; then
    BRANDING_DIR=/usr/local/share/dsh/branding
  else
    BRANDING_DIR="$SCRIPT_DIR/branding"
  fi
fi
[[ -d "$BRANDING_DIR" ]] || fail "branding directory is missing: $BRANDING_DIR"

PLUGIN_DIR="${DSH_BRAND_PLUGIN_DIR:-}"
if [[ -z "$PLUGIN_DIR" ]]; then
  if [[ -d /usr/local/share/dsh/plugins/imc-brand ]]; then
    PLUGIN_DIR=/usr/local/share/dsh/plugins/imc-brand
  else
    PLUGIN_DIR="$SCRIPT_DIR/plugins/imc-brand"
  fi
fi
[[ -f "$PLUGIN_DIR/package.json" ]] || fail "brand plugin is missing: $PLUGIN_DIR"

if ! command -v dsh >/dev/null 2>&1; then
  fail "dsh is not on PATH"
fi
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is required to apply branding"
fi

eval "$(
  python3 - "$BRANDING_DIR" "$PLUGIN_DIR" <<'PY'
import json
import pathlib
import shlex
import sys

branding = pathlib.Path(sys.argv[1])
plugin_dir = pathlib.Path(sys.argv[2])
values = {"productName": "IMC Montan AI", "logoFile": "logo.svg", "plugin": "imc-dsh-brand"}
brand_file = branding / "brand.yaml"
if brand_file.is_file():
    for raw in brand_file.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in values:
            values[key] = value.strip().strip("'\"")
manifest = json.loads((plugin_dir / "package.json").read_text(encoding="utf-8"))
print(f"PRODUCT_NAME={shlex.quote(values['productName'])}")
print(f"LOGO_FILE={shlex.quote(values['logoFile'])}")
print(f"PLUGIN_NAME={shlex.quote(values['plugin'])}")
print(f"PLUGIN_VERSION={shlex.quote(str(manifest.get('version') or '1.0.0'))}")
PY
)"

DEST_DIR="$DSH_HOME/branding"
DEST_LOGO="$DEST_DIR/${LOGO_FILE}"
PATCH_FILE="$DSH_HOME/profiles/web/cordis.patch.yml"
PROFILE_PKG="$DSH_HOME/profiles/web/package.json"

LOGO_SRC="${DSH_BRAND_LOGO_SOURCE:-}"
if [[ -z "$LOGO_SRC" || ! -f "$LOGO_SRC" ]]; then
  LOGO_SRC="$BRANDING_DIR/$LOGO_FILE"
fi
[[ -f "$LOGO_SRC" ]] || fail "logo file is missing: $LOGO_SRC"

mkdir -p "$DEST_DIR" "$DSH_HOME/profiles/web"
cp "$LOGO_SRC" "$DEST_LOGO"
chmod 0644 "$DEST_LOGO"

if [[ ! -f "$PROFILE_PKG" ]]; then
  log "initializing web profile"
  dsh --profile web --dump-config >/dev/null
fi
[[ -f "$PROFILE_PKG" ]] || fail "web profile was not created at $PROFILE_PKG"

need_plugin=1
if python3 - "$PROFILE_PKG" "$PLUGIN_NAME" "$PLUGIN_VERSION" <<'PY'
import json
import sys
from pathlib import Path

package_path, plugin_name, wanted = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    data = json.loads(package_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    sys.exit(1)
if plugin_name not in (data.get("dependencies") or {}):
    sys.exit(1)
bundles = ((data.get("dsh") or {}).get("profile") or {}).get("bundles") or []
if plugin_name not in bundles:
    sys.exit(1)
manifest = package_path.parent / "node_modules" / plugin_name / "package.json"
if not manifest.is_file():
    sys.exit(1)
try:
    version = str(json.loads(manifest.read_text(encoding="utf-8")).get("version") or "")
except (OSError, json.JSONDecodeError):
    sys.exit(1)
sys.exit(0 if version == wanted else 1)
PY
then
  need_plugin=0
fi

if [[ "$need_plugin" -eq 1 ]]; then
  log "installing ${PLUGIN_NAME}@${PLUGIN_VERSION} from $PLUGIN_DIR"
  dsh plugin --profile web add -w "$PLUGIN_DIR"
fi

python3 - "$PATCH_FILE" "$PRODUCT_NAME" "$DEST_LOGO" <<'PY'
from pathlib import Path
import json
import sys

patch_path = Path(sys.argv[1])
product_name = json.dumps(sys.argv[2], ensure_ascii=False)
logo_path = json.dumps(sys.argv[3], ensure_ascii=False)
patch_path.parent.mkdir(parents=True, exist_ok=True)
patch_path.write_text(
    (
        "# Managed by deploy/dsh/apply-brand.sh. Other web-profile patches belong\n"
        "# in $DSH_HOME/cordis.patch.yml so a brand refresh does not wipe them.\n"
        "- id: ui-brand-official\n"
        "  disabled: true\n"
        "- id: imc-dsh-brand\n"
        "  config:\n"
        f"    productName: {product_name}\n"
        f"    logoPath: {logo_path}\n"
        f"    logoAlt: {product_name}\n"
    ),
    encoding="utf-8",
)
PY

log "web UI brand is ${PRODUCT_NAME} (${DEST_LOGO})"
