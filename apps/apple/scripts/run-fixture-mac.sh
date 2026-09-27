#!/usr/bin/env bash
# Launch the macOS debug build straight into the Old Hundredth fixture score (apps/fixtures).
# Usage: scripts/run-fixture-mac.sh [extra app arguments]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$HERE/build/DerivedData/Build/Products/Debug/BrasscribePlay.app/Contents/MacOS/BrasscribePlay"
export BRASSCRIBE_FIXTURES="${BRASSCRIBE_FIXTURES:-$ROOT/apps/fixtures/old-hundredth}"
[ -f "$ROOT/data/soundfonts/MuseScore_General.sf2" ] && export BRASSCRIBE_SOUNDFONT="$ROOT/data/soundfonts/MuseScore_General.sf2"
[ -f "$ROOT/sounds/mapping.json" ] && export BRASSCRIBE_SOUNDS="$ROOT"
exec "$APP" -reset -open-fixture-score "$@"
