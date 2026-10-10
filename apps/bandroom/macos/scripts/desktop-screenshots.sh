#!/usr/bin/env bash
# Screenshots of the real popover from the menu bar and the Pair window, light and dark, English and bokmål, with
# canned demo data (Debug build, no engine): scripts/desktop-screenshots.sh OUTDIR
# It runs the app on the desktop and clicks its menu-bar item, so run it in the macOS VM (docs/dev/macos-vm.md), not on
# a Mac in use. The screen catalogue (scripts/screenshots.sh) draws the same screens off screen.
# Needs Accessibility permission for the terminal (System Events opens the menu-bar item).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:?output directory}"
mkdir -p "$OUT"
DATA="$(mktemp -d)"

BIN="$(cd "$HERE/.." && pwd)/build/DerivedData/Build/Products/Debug/Brasscribe Bandroom.app/Contents/MacOS/Brasscribe Bandroom"
# Demo instances run no engine, so ending them outright is safe.
quit() { pkill -f "$BIN" >/dev/null 2>&1 || true; sleep 2; }
click_icon() { osascript -e 'tell application "System Events" to tell process "Brasscribe Bandroom" to click menu bar item 1 of menu bar 2' >/dev/null; sleep 2; }

shoot() {  # appearance lang demo suffix [--request]
  local appearance="$1" lang="$2" demo="$3" suffix="$4"; shift 4
  quit
  "$HERE/run-dev.sh" --data "$DATA" --logs "$DATA/logs" --appearance "$appearance" --lang "$lang" --demo "$demo" --open pair "$@"
  sleep 6
  "$HERE/shot.sh" "" "$OUT/pair-$suffix.png" || "$HERE/shot.sh" "Pair" "$OUT/pair-$suffix.png"
  for _ in 1 2 3; do
    click_icon
    "$HERE/shot.sh" popover "$OUT/popover-$suffix.png" 2>/dev/null && break
  done
}

shoot light en busy busy-light
shoot dark en busy busy-dark
shoot light nb busy busy-nb-light
shoot light en idle idle-request-light --request
quit
rm -rf "$DATA"
ls "$OUT"
