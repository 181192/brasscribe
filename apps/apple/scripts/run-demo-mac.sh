#!/usr/bin/env bash
# Launch the macOS debug build straight into the golden Mikkel score (demo fixture).
# Usage: scripts/run-demo-mac.sh [extra app arguments]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$HERE/build/DerivedData/Build/Products/Debug/BrasscribePlay.app/Contents/MacOS/BrasscribePlay"
export BRASSCRIBE_FIXTURES="${BRASSCRIBE_FIXTURES:-$ROOT/data/golden/mikkel-arranged-band}"
[ -f "$ROOT/data/soundfonts/MuseScore_General.sf2" ] && export BRASSCRIBE_SOUNDFONT="$ROOT/data/soundfonts/MuseScore_General.sf2"
exec "$APP" -reset -open-demo-score "$@"
