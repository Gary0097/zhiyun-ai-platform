#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x "apps/qwenpaw-embedded/runtime/qwenpaw/bin/qwenpaw" ] && ! command -v qwenpaw >/dev/null 2>&1; then
  echo "Project QwenPaw runtime is missing. Run ./setup-ai-os.sh once." >&2
  exit 1
fi
exec node apps/qwenpaw-embedded/scripts/start.mjs
