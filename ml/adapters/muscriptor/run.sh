#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>
# Env: MUSCRIPTOR_MODEL=small|medium|large, MUSCRIPTOR_INSTRUMENTS=trumpet,trombone,... (optional)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
set -- "$1" -m "${MUSCRIPTOR_MODEL:-medium}" -o "$2" --detect-tempo false
[ -n "${MUSCRIPTOR_INSTRUMENTS:-}" ] && set -- "$@" --instruments "$MUSCRIPTOR_INSTRUMENTS"
uv run --project "$here" muscriptor transcribe "$@" >/dev/null 2>&1
