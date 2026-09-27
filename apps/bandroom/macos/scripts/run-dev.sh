#!/usr/bin/env bash
# Launches the built app the way Finder does (bare environment, via `open`), against a checkout.
#   scripts/run-dev.sh [--data DIR] [--logs DIR] [--appearance light|dark] [--open main,pair] [--lang nb]
#                      [--demo busy|idle] [--request]   (Debug: canned data for screenshots, no engine)
# CHECKOUT (default: this repository) must have its pixi default environment installed.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HERE/build/DerivedData/Build/Products/Debug/Brasscribe Bandroom.app"
CHECKOUT="${CHECKOUT:-$(cd "$HERE/../../.." && pwd)}"
args=(--env "BRASSCRIBE_CHECKOUT=$CHECKOUT" --env BANDROOM_NO_LOGIN_ITEM=1)
lang=()
while [ $# -gt 0 ]; do
  case "$1" in
    --data) args+=(--env "BRASSCRIBE_DATA=$2"); shift 2 ;;
    --logs) args+=(--env "BRASSCRIBE_LOGS=$2"); shift 2 ;;
    --appearance) args+=(--env "BANDROOM_APPEARANCE=$2"); shift 2 ;;
    --open) args+=(--env "BANDROOM_OPEN=$2"); shift 2 ;;
    --demo) args+=(--env "BANDROOM_DEMO=$2"); shift 2 ;;
    --request) args+=(--env BANDROOM_DEMO_REQUEST=1); shift ;;
    --lang) lang=(--args -AppleLanguages "($2)"); shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
open -n "${args[@]}" "$APP" ${lang[@]+"${lang[@]}"}
