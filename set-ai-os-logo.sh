#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ "$#" -ne 1 ]; then
  echo "用法：./set-ai-os-logo.sh <png|jpg|svg|webp>，或 --reset 恢复默认。" >&2
  exit 1
fi
exec node apps/qwenpaw-embedded/scripts/set-logo.mjs "$1"
