#!/usr/bin/env bash
# 灵泽万川智造云 一键安装（Linux，在线模式）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  灵泽万川智造云 一键安装（在线模式）"
echo "============================================"

command -v node >/dev/null 2>&1 || { echo "[错误] 未检测到 Node.js（需要 20 或以上）：https://nodejs.org"; exit 1; }
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "$NODE_MAJOR" -lt 20 ]; then echo "[错误] Node.js 版本过低（当前 $(node -v)，需要 ≥ 20）"; exit 1; fi
command -v git >/dev/null 2>&1 || echo "[提示] 未检测到 Git：核心安装与启动不受影响（仅在线拉取可选更新时需要）。"

echo "[1/3] 安装运行时与锁定应用（首次约 3-10 分钟）..."
bash ./setup-ai-os.sh

echo "[2/3] 启动服务（后台运行，日志见 ai-os-install.log）..."
nohup bash ./start-ai-os.sh > ai-os-install.log 2>&1 &
echo $! > ai-os-install.pid

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
