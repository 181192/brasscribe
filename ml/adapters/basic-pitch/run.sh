#!/bin/sh
# Adapter contract: run.sh <input.wav> <output.mid>
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
uv run --project "$here" basic-pitch "$tmp" "$1" >/dev/null 2>&1
mv "$tmp"/*.mid "$2"
rmdir "$tmp"
