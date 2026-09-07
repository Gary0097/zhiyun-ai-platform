#!/usr/bin/env bash
# 灵泽万川智造云 AI-OS — QwenPaw Hub 运行环境供给（Linux/macOS）
# 创建/修复 apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv（qwenpaw[hub]==锁版本）。
set -euo pipefail
cd "$(dirname "$0")"

EMBEDDED="apps/zhizaoyunAIOS"
# 与 setup-ai-os.sh 相同：用 Node 读锁文件，避免依赖系统 python3
VERSION=$(node -e "const x=require(process.argv[1]); process.stdout.write(x.version)" "$EMBEDDED/qwenpaw.lock.json")
RUNTIME_CACHE="$EMBEDDED/runtime/cache"
HUB_VENV="$EMBEDDED/runtime/qwenpaw-hub/venv"
HUB_QWENPAW="$HUB_VENV/bin/qwenpaw"
CACHED_UV="$RUNTIME_CACHE/bin/uv"

brand_hub_console() {
  # Hub 控制台品牌化（智造云 AIOS 风格；失败不阻断，可重跑）——升级后
  # venv 已就绪的早退路径同样需要执行，否则重装/升级会回退为上游默认外观
  local console="$HUB_VENV/lib/python3.12/site-packages/qwenpaw/console"
  if command -v node >/dev/null 2>&1 && [ -f "$EMBEDDED/scripts/patch-console-ui.mjs" ] && [ -f "$console/index.html" ]; then
    node "$EMBEDDED/scripts/patch-console-ui.mjs" --console-dir "$console" || echo "提示：Hub 控制台品牌化未完成，可重跑 setup-hub.sh。"
  fi
}

# hub 子命令探测：基础包装好但 [hub] 附加依赖缺一半时 --version 仍成功
if [ -x "$HUB_QWENPAW" ] && "$HUB_QWENPAW" --version 2>/dev/null | grep -q "version $VERSION\$" && "$HUB_QWENPAW" hub --help >/dev/null 2>&1; then
  echo "QwenPaw Hub $VERSION 运行环境已就绪：$HUB_VENV"
  brand_hub_console
  exit 0
fi

UV_CMD="$CACHED_UV"
if [ ! -x "$UV_CMD" ]; then
  if command -v uv >/dev/null 2>&1; then UV_CMD="$(command -v uv)"
  elif [ "${ZAIOS_OFFLINE:-0}" = "1" ]; then
    echo "未找到 uv；离线模式无法引导安装，请先在联网环境运行一次安装生成缓存。" >&2
    exit 1
  else
    # 在线引导 uv（与 setup-ai-os.sh 一致）：装进缓存目录，不改 PATH
    echo "正在联网引导安装 uv ..."
    mkdir -p "$(dirname "$CACHED_UV")"
    if curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$(cd "$(dirname "$CACHED_UV")" && pwd)" sh; then
      UV_CMD="$CACHED_UV"
    else
      echo "uv 引导安装失败。" >&2; exit 1
    fi
    [ -x "$UV_CMD" ] || { echo "uv 引导安装失败。" >&2; exit 1; }
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

brand_hub_console
echo "QwenPaw Hub $VERSION 运行环境安装完成：$HUB_VENV"
