#!/usr/bin/env bash
# 灵泽万川智造云 Hub（局域网多用户）
cd "$(dirname "$0")"
echo "=============================================="
echo "  灵泽万川智造云 Hub — 局域网多用户模式"
echo "  首次使用：本机打开 http://127.0.0.1:8000 注册"
echo "  第一个注册的账号自动成为管理员"
echo "=============================================="
export PYTHONIOENCODING=utf-8
exec ./apps/qwenpaw-embedded/runtime/qwenpaw/venv/Scripts/qwenpaw hub --host 0.0.0.0 --port 8000 --force-public --config hub.yaml
