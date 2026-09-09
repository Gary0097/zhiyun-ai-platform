#!/usr/bin/env bash
# 灵泽万川智造云 Hub（局域网多用户）
set -euo pipefail
cd "$(dirname "$0")"
if [ -x ./extras/node/bin/node ]; then export PATH="$PWD/extras/node/bin:$PATH"; fi
echo "=============================================="
echo "  灵泽万川智造云 Hub — 局域网多用户模式"
echo "  首次使用：本机打开 http://127.0.0.1:8000 注册"
echo "  第一个注册的账号自动成为管理员"
echo "=============================================="
export PYTHONIOENCODING=utf-8
# Hub 数据（数据库/密钥，见 hub.yaml）固定落在安装目录下，避免随用户主目录漂移
export QWENPAW_WORKING_DIR="${PWD}/apps/zhizaoyunAIOS/workspace"
mkdir -p "$QWENPAW_WORKING_DIR"
# 每次启动都做版本/完整性校验（setup-hub.sh 内置版本比对，就绪时秒退）；
# 离线包标记存在时才强制离线安装
if [ -f ./apps/zhizaoyunAIOS/runtime/cache/OFFLINE-PACKAGE ]; then export ZAIOS_OFFLINE=1 UV_OFFLINE=1; fi
bash ./setup-hub.sh || exit 1
HUB_BIN=./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/bin/qwenpaw
[ -x "$HUB_BIN" ] || HUB_BIN=./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/Scripts/qwenpaw
# Local 隔离预检：Linux 需要 Bubblewrap（官方要求），缺失仅警告
command -v bwrap >/dev/null 2>&1 || echo "[WARN] bwrap (Bubblewrap) not found: Local runtimes will fail to start. Install it (e.g. apt install bubblewrap)."
# 派生配置：public_base_url 用本机局域网 IPv4（OAuth/MCP 回调需与浏览器可见地址一致）
node apps/zhizaoyunAIOS/scripts/hub-config.mjs
HUB_HOST=$("$(dirname "$HUB_BIN")/python" apps/zhizaoyunAIOS/scripts/hub-bind-host.py)
if [ "$HUB_HOST" = '127.0.0.1' ]; then
  echo "首次初始化仅允许本机访问 http://127.0.0.1:8000；创建管理员后重新启动 Hub，开放团队访问。"
fi
exec "$HUB_BIN" hub --host "$HUB_HOST" --port 8000 --force-public --config hub.runtime.yaml
