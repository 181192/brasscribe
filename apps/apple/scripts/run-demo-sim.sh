#!/usr/bin/env bash
# Build, install and launch the demo score on a simulator, then optionally screenshot it.
# Usage: scripts/run-demo-sim.sh "iPhone 17" [screenshot.png] [extra app args...]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
DEVICE="$1"; SHOT="${2:-}"; shift; [ $# -gt 0 ] && shift
APP="$HERE/build/DerivedData/Build/Products/Debug-iphonesimulator/BrasscribePlay.app"
cd "$HERE"
xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribePlay-iOS \
  -destination "platform=iOS Simulator,name=$DEVICE" build -quiet
xcrun simctl boot "$DEVICE" 2>/dev/null || true
xcrun simctl bootstatus "$DEVICE" >/dev/null
xcrun simctl terminate "$DEVICE" no.brasscribe.play 2>/dev/null || true
xcrun simctl install "$DEVICE" "$APP"
export SIMCTL_CHILD_BRASSCRIBE_FIXTURES="$ROOT/data/golden/mikkel-arranged-band"
[ -f "$ROOT/data/soundfonts/MuseScore_General.sf2" ] && export SIMCTL_CHILD_BRASSCRIBE_SOUNDFONT="$ROOT/data/soundfonts/MuseScore_General.sf2"
[ -f "$ROOT/sounds/mapping.json" ] && export SIMCTL_CHILD_BRASSCRIBE_SOUNDS="$ROOT"
xcrun simctl launch "$DEVICE" no.brasscribe.play -reset -open-demo-score "$@"
if [ -n "$SHOT" ]; then
  sleep "${WAIT:-15}"
  xcrun simctl io "$DEVICE" screenshot "$SHOT"
fi
