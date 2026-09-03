#!/usr/bin/env bash
# 灵泽万川智造云 Hub（局域网多用户）
cd "$(dirname "$0")"
echo "=============================================="
echo "  灵泽万川智造云 Hub — 局域网多用户模式"
echo "  首次使用：本机打开 http://127.0.0.1:8000 注册"
echo "  第一个注册的账号自动成为管理员"
echo "=============================================="
export PYTHONIOENCODING=utf-8
# Hub 运行环境缺失时自动供给
if [ ! -x ./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/bin/qwenpaw ] && [ ! -x ./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/Scripts/qwenpaw ]; then
  echo "[提示] 首次运行：正在安装 QwenPaw Hub 运行环境（数分钟）..."
  bash ./setup-hub.sh || exit 1
fi
HUB_BIN=./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/bin/qwenpaw
[ -x "$HUB_BIN" ] || HUB_BIN=./apps/zhizaoyunAIOS/runtime/qwenpaw-hub/venv/Scripts/qwenpaw
exec "$HUB_BIN" hub --host 0.0.0.0 --port 8000 --force-public --config hub.yaml
