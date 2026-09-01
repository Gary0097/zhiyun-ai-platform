#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
# U盘离线包内置的便携 Node 优先于系统 Node（不存在时无影响）
if [ -x "extras/node/node" ]; then PATH="$(pwd)/extras/node:$PATH"; export PATH; fi
if [ ! -x "apps/qwenpaw-embedded/runtime/qwenpaw/venv/bin/qwenpaw" ] && [ ! -x "apps/qwenpaw-embedded/runtime/qwenpaw/bin/qwenpaw" ] && ! command -v qwenpaw >/dev/null 2>&1; then
  echo "Project QwenPaw runtime is missing. Run ./setup-ai-os.sh once." >&2
  exit 1
fi
exec node apps/qwenpaw-embedded/scripts/start.mjs
