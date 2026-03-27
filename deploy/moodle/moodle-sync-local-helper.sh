#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/sergei/ai_appdir/ai_app}"
SOURCE_DIR="${SOURCE_DIR:-$APP_ROOT/deploy/moodle/local/imc_sso}"
TARGET_DIR="${TARGET_DIR:-/opt/moodle/local/imc_sso}"

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "moodle-sync-local-helper: missing source file: $path" >&2
    exit 1
  fi
}

require_file "$SOURCE_DIR/version.php"
require_file "$SOURCE_DIR/logout_first.php"

install -d -m 2750 "$TARGET_DIR"
install -m 644 "$SOURCE_DIR/version.php" "$TARGET_DIR/version.php"
install -m 644 "$SOURCE_DIR/logout_first.php" "$TARGET_DIR/logout_first.php"

echo "moodle-sync-local-helper: restored local_imc_sso into $TARGET_DIR"
