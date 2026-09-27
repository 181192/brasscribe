#!/usr/bin/env bash
# Screenshot a Bandroom window by title: scripts/shot.sh "Pair a phone" out.png
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
id="$(swift "$HERE/window-id.swift" "$1")"
screencapture -l "$id" -o "$2"
echo "$2"
