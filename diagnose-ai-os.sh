#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec node apps/qwenpaw-embedded/scripts/doctor.mjs "$@"
