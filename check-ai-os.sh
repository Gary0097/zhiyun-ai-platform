#!/usr/bin/env bash
# 健康检查入口（保留跨平台维护入口，实际诊断由 doctor.mjs 承载）
cd "$(dirname "$0")"
node apps/zhizaoyunAIOS/scripts/doctor.mjs
