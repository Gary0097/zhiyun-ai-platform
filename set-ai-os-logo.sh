#!/usr/bin/env bash
# Logo 维护入口（兼容 QUICKSTART 文档）：set-ai-os-logo.sh <图片路径> | --reset
cd "$(dirname "$0")"
BRAND="apps/zhizaoyunAIOS/workspace/branding"
mkdir -p "$BRAND"
if [ "$1" = "--reset" ]; then rm -f "$BRAND/logo.json"; echo "[OK] Logo 已恢复默认（重启服务后生效）。"; exit 0; fi
if [ -z "$1" ] || [ ! -f "$1" ]; then echo "用法：$0 <图片路径|--reset>"; exit 1; fi
case "${1##*.}" in
  png) MIME=image/png;; jpg|jpeg) MIME=image/jpeg;; svg) MIME=image/svg+xml;; webp) MIME=image/webp;; *) MIME=image/png;;
esac
cp -f "$1" "$BRAND/custom-logo.${1##*.}"
printf '{"path": "/", "mime": ""}' "$(cd "$BRAND" && pwd)" "custom-logo.${1##*.}" "$MIME" > "$BRAND/logo.json"
echo "[OK] Logo 已设置（重启服务后生效，--reset 可恢复默认）。"
