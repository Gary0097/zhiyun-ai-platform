#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
node apps/zhizaoyunAIOS/scripts/health-report.mjs
