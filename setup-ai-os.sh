#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EMBEDDED_ROOT="$PROJECT_ROOT/apps/zhizaoyunAIOS"
LOCK="$EMBEDDED_ROOT/qwenpaw.lock.json"
VERSION=$(node -e "const x=require(process.argv[1]); process.stdout.write(x.version)" "$LOCK")
RUNTIME_REL=$(node -e "const x=require(process.argv[1]); process.stdout.write(x.runtime_dir)" "$LOCK")
RUNTIME_ROOT="$EMBEDDED_ROOT/$RUNTIME_REL"
CACHE_DIR=${AI_OS_RUNTIME_CACHE:-"$EMBEDDED_ROOT/runtime/cache"}
VENV_ROOT="$RUNTIME_ROOT/venv"
QWENPAW="$VENV_ROOT/bin/qwenpaw"
PYTHON="$VENV_ROOT/bin/python"
CACHED_UV="$CACHE_DIR/bin/uv"
OFFLINE=${AI_OS_OFFLINE:-0}
if [ -x "$PYTHON" ] && "$PYTHON" --version >/dev/null 2>&1 && [ -x "$QWENPAW" ] && "$QWENPAW" --version 2>&1 | grep -E "version[[:space:]]+$VERSION[[:space:]]*$" >/dev/null; then
  # 升级路径：运行时就绪但可能缺少后续新增的 Creator 依赖，补装后再退出
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$PYTHON" pypdfium2 pandas openpyxl matplotlib tabulate >/dev/null 2>&1 || true
  fi
  printf 'QwenPaw %s 项目运行环境已就绪：%s\n' "$VERSION" "$RUNTIME_ROOT"; exit 0
fi
mkdir -p "$CACHE_DIR/bin" "$CACHE_DIR/uv" "$CACHE_DIR/python"
if [ -x "$CACHED_UV" ]; then UV="$CACHED_UV"
elif command -v uv >/dev/null 2>&1; then cp "$(command -v uv)" "$CACHED_UV"; chmod +x "$CACHED_UV"; UV="$CACHED_UV"
elif [ "$OFFLINE" = "1" ]; then printf '离线缓存中没有 uv：%s。请先在联网环境运行一次 setup-ai-os.sh。\n' "$CACHED_UV" >&2; exit 1
else
  curl -fsSL https://astral.sh/uv/install.sh -o "$CACHE_DIR/uv-install.sh"
  UV_INSTALL_DIR="$CACHE_DIR/bin" UV_NO_MODIFY_PATH=1 sh "$CACHE_DIR/uv-install.sh"
  UV="$CACHED_UV"
fi
export UV_CACHE_DIR="$CACHE_DIR/uv" UV_PYTHON_INSTALL_DIR="$CACHE_DIR/python" UV_PYTHON_PREFERENCE=only-managed
if [ "$OFFLINE" = "1" ]; then export UV_OFFLINE=1; fi
"$UV" venv "$VENV_ROOT" --python 3.12 --clear
"$UV" pip install --python "$PYTHON" "qwenpaw==$VERSION"   || exit 1
# Creator 可选依赖：离线缺失时跳过（官方设计为优雅降级），不阻断安装
"$UV" pip install --python "$PYTHON" pypdfium2 pandas openpyxl matplotlib tabulate >/dev/null 2>&1   || echo "提示：Creator 可选依赖未安装（离线缓存缺失），原版 Creator 文档渲染将降级，不影响核心功能。"
if [ ! -x "$QWENPAW" ] || ! "$QWENPAW" --version 2>&1 | grep -E "version[[:space:]]+$VERSION[[:space:]]*$" >/dev/null; then
  printf '项目运行环境安装后版本校验失败。\n' >&2; exit 1
fi
printf 'QwenPaw %s 项目运行环境安装完成：%s\n' "$VERSION" "$RUNTIME_ROOT"
