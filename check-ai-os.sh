#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
node apps/qwenpaw-embedded/scripts/health-report.mjs
