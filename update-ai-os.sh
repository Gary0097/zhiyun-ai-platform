#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Linux intentionally checks/downloads only; never run a Windows installer.
# Use the existing Linux maintenance entries after a stopped-service backup.
exec node "$ROOT/scripts/updates/client.mjs" "${1:-check}"
