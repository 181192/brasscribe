#!/usr/bin/env bash
# Runs the BandroomKit unit tests: scripts/test-kit.sh [filter]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
cd "$HERE/../Packages/BandroomKit"
if [ $# -gt 0 ]; then
  exec swift test --filter "$1"
fi
exec swift test
