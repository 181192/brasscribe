#!/usr/bin/env bash
# Launches the built app the way Finder does (bare environment, via `open`), against a checkout.
#   scripts/run-dev.sh [--data DIR] [--logs DIR] [--appearance light|dark] [--open main,pair] [--lang nb]
#                      [--demo busy|idle] [--request]   (Debug: canned data for screenshots, no engine)
# CHECKOUT (default: this repository) must have its pixi default environment installed.
# The data and logs folders default to build/dev, not the installed Bandroom's: sharing its data folder, this
# instance would take the other one's engine for a leftover and stop it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HERE/build/DerivedData/Build/Products/Debug/Brasscribe Bandroom.app"
CHECKOUT="${CHECKOUT:-$(cd "$HERE/../../.." && pwd)}"
args=(--env "BRASSCRIBE_CHECKOUT=$CHECKOUT" --env BANDROOM_NO_LOGIN_ITEM=1)
data="$HERE/build/dev/data"
logs="$HERE/build/dev/logs"
lang=()
while [ $# -gt 0 ]; do
  case "$1" in
    --data) data="$2"; shift 2 ;;
    --logs) logs="$2"; shift 2 ;;
    --appearance) args+=(--env "BANDROOM_APPEARANCE=$2"); shift 2 ;;
    --open) args+=(--env "BANDROOM_OPEN=$2"); shift 2 ;;
    --demo) args+=(--env "BANDROOM_DEMO=$2"); shift 2 ;;
    --request) args+=(--env BANDROOM_DEMO_REQUEST=1); shift ;;
    --lang) lang=(--args -AppleLanguages "($2)"); shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
args+=(--env "BRASSCRIBE_DATA=$data" --env "BRASSCRIBE_LOGS=$logs")
open -n "${args[@]}" "$APP" ${lang[@]+"${lang[@]}"}
