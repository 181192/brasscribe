#!/usr/bin/env bash
# Screenshot the running Brasscribe Play window on macOS: scripts/shot-mac.sh out.png
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
id="$(swift "$HERE/window-id.swift" Brasscribe)"
screencapture -l "$id" -o "$1"
echo "$1"
