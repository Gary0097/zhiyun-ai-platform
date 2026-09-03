#!/usr/bin/env bash
# 灵泽万川智造云 AI-OS — QwenPaw Hub 运行环境供给（Linux/macOS）
# 创建/修复 apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv（qwenpaw[hub]==锁版本）。
set -euo pipefail
cd "$(dirname "$0")"

EMBEDDED="apps/zhizaoyunAIOS"
VERSION=$(python3 -c "import json;print(json.load(open('$EMBEDDED/qwenpaw.lock.json'))['version'])")
RUNTIME_CACHE="$EMBEDDED/runtime/cache"
HUB_VENV="$EMBEDDED/runtime/qwenpaw-hub/venv"
HUB_QWENPAW="$HUB_VENV/bin/qwenpaw"
CACHED_UV="$RUNTIME_CACHE/bin/uv"

if [ -x "$HUB_QWENPAW" ] && "$HUB_QWENPAW" --version 2>/dev/null | grep -q "version $VERSION\$"; then
  echo "QwenPaw Hub $VERSION 运行环境已就绪：$HUB_VENV"
  exit 0
fi

UV_CMD="$CACHED_UV"
if [ ! -x "$UV_CMD" ]; then
  if command -v uv >/dev/null 2>&1; then UV_CMD="$(command -v uv)"
  else
    echo "未找到 uv；联网环境可先运行安装脚本生成缓存。" >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "$CACHED_UV")" "$RUNTIME_CACHE/uv" "$RUNTIME_CACHE/python"
UV_CACHE_DIR="$RUNTIME_CACHE/uv" \
UV_PYTHON_INSTALL_DIR="$RUNTIME_CACHE/python" \
UV_PYTHON_PREFERENCE=only-managed \
  "$UV_CMD" venv "$HUB_VENV" --python 3.12 --clear
UV_CACHE_DIR="$RUNTIME_CACHE/uv" \
UV_PYTHON_INSTALL_DIR="$RUNTIME_CACHE/python" \
UV_PYTHON_PREFERENCE=only-managed \
  "$UV_CMD" pip install --python "$HUB_VENV/bin/python" "qwenpaw[hub]==$VERSION"

"$HUB_QWENPAW" --version | grep -q "version $VERSION\$" || { echo "Hub 环境安装后版本校验失败" >&2; exit 1; }
echo "QwenPaw Hub $VERSION 运行环境安装完成：$HUB_VENV"
