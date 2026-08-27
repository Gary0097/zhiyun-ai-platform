#!/usr/bin/env bash
# 制造云 AI-OS 一键安装（Linux，在线模式）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  制造云 AI-OS 一键安装（在线模式）"
echo "============================================"

command -v node >/dev/null 2>&1 || { echo "[错误] 未检测到 Node.js（需要 20 或以上）：https://nodejs.org"; exit 1; }
command -v git  >/dev/null 2>&1 || { echo "[错误] 未检测到 Git：https://git-scm.com/download/linux"; exit 1; }

echo "[1/3] 安装运行时与锁定应用（首次约 3-10 分钟）..."
./setup-ai-os.sh

echo "[2/3] 启动服务..."
./start-ai-os.sh

echo "[3/3] 等待服务就绪..."
for i in $(seq 1 40); do
  if curl -sf --max-time 2 http://127.0.0.1:8088/api/version >/dev/null 2>&1; then
    echo "服务已就绪：http://127.0.0.1:8088"
    exit 0
  fi
  sleep 3
done
echo "服务未在预期时间内就绪，请稍后手动访问 http://127.0.0.1:8088"
exit 0
