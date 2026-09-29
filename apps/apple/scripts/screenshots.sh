#!/usr/bin/env bash
# Screenshots of every key screen, light and dark, into docs/screenshots/.
# Usage: scripts/screenshots.sh mac|iphone|ipad [screen …]     (NB=1 for Norwegian, named …-nb-…;
#        CONNECTION=offline|reconnecting|needs-pairing for another connection row, default connected;
#        SIM_DEVICE=<udid or name> shoots on that simulator instead of the shared "iPhone 17" / iPad Air)
# Build first (make build, or xcodebuild … build). The macOS build can carry another bundle
# id (PLAY_BUNDLE_ID=…) so it runs beside another copy of the app.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
OUT="$HERE/docs/screenshots"
mkdir -p "$OUT"
TARGET="$1"; shift
SCREENS=("$@")
[ ${#SCREENS[@]} -eq 0 ] && SCREENS=(home home-full source transcribing transcribing-cancel review review-listening finish-later output score part export first-run error)
FIXTURES="$ROOT/apps/fixtures/old-hundredth"
SF="$ROOT/data/soundfonts/MuseScore_General.sf2"
WAIT="${WAIT:-12}"
LANGARGS=(); TAG=""
if [ "${NB:-0}" = 1 ]; then LANGARGS=(-AppleLanguages "(nb)" -AppleLocale nb_NO); TAG="-nb"; fi
# the connection row shows a fixed state (connected|reconnecting|offline|needs-pairing); the default is
# "connected", so no Brasscribe running on this Mac changes the pictures
LANGARGS+=(-connection "${CONNECTION:-connected}")

shoot_mac() {   # screen appearance
  # through Launch Services: a child of this shell is refused activation and opens no window
  local app="$HERE/build/DerivedData/Build/Products/Debug/BrasscribePlay.app"
  open -n -F "$app" --env BRASSCRIBE_FIXTURES="$FIXTURES" --env BRASSCRIBE_SOUNDFONT="$SF" \
    --env BRASSCRIBE_COMPANION="http://127.0.0.1:1" --args -reset -skip-first-run -screen "$1" -appearance "$2" "${LANGARGS[@]}"
  sleep "$WAIT"
  local pid
  pid=$(pgrep -n -f "$app/Contents/MacOS/BrasscribePlay")
  local id
  if id=$(swift "$HERE/scripts/window-of-pid.swift" "$pid"); then
    screencapture -l "$id" -o "$OUT/macos$TAG-$1-$2.png" && echo "macos$TAG-$1-$2.png"
  else
    echo "macos-$1-$2: no window" >&2
  fi
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

shoot_sim() {   # device prefix screen appearance
  local dev="$1" name="$2" screen="$3" look="$4"
  local app="$HERE/build/DerivedData/Build/Products/Debug-iphonesimulator/BrasscribePlay.app"
  xcrun simctl boot "$dev" 2>/dev/null || true
  xcrun simctl bootstatus "$dev" >/dev/null
  xcrun simctl status_bar "$dev" override --time 9:41 --batteryState charged --batteryLevel 100 2>/dev/null || true
  xcrun simctl ui "$dev" appearance "$look" 2>/dev/null || true
  xcrun simctl terminate "$dev" no.brasscribe.play 2>/dev/null || true
  xcrun simctl install "$dev" "$app"
  SIMCTL_CHILD_BRASSCRIBE_FIXTURES="$FIXTURES" SIMCTL_CHILD_BRASSCRIBE_SOUNDFONT="$SF" SIMCTL_CHILD_BRASSCRIBE_COMPANION="http://127.0.0.1:1" \
    xcrun simctl launch "$dev" no.brasscribe.play -reset -skip-first-run -screen "$screen" -appearance "$look" "${LANGARGS[@]}" >/dev/null
  # the score screens engrave first
  case "$screen" in score|part|export) sleep $((WAIT + 14)) ;; *) sleep "$WAIT" ;; esac
  xcrun simctl io "$dev" screenshot "$OUT/$name$TAG-$screen-$look.png" >/dev/null 2>&1 && echo "$name$TAG-$screen-$look.png"
}

for s in "${SCREENS[@]}"; do
  for look in light dark; do
    case "$TARGET" in
      mac) shoot_mac "$s" "$look" ;;
      iphone) shoot_sim "${SIM_DEVICE:-iPhone 17}" iphone "$s" "$look" ;;
      ipad) shoot_sim "${SIM_DEVICE:-iPad Air 11-inch (M4)}" ipad "$s" "$look" ;;
    esac
  done
done
