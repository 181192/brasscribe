#!/bin/bash
# Runs before XcodeGen generates Fretscribe's project: alphaTab for the tab page, and the app icon from the design
# system (design/brands/fretscribe/dist/icons/apple), copied into a generated catalog (App/Icon.xcassets, not committed).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
"$HERE/scripts/fetch-alphatab.sh"
APP="$HERE/products/fretscribe/App"
ICONS="$HERE/../../design/brands/fretscribe/dist/icons/apple/AppIcon.appiconset"
[ -d "$ICONS" ] || { echo "error: no app icon at $ICONS (uv run design/brands/fretscribe/brand/build.py)" >&2; exit 1; }
mkdir -p "$APP/Icon.xcassets"
rm -rf "$APP/Icon.xcassets/AppIcon.appiconset"
cp -R "$ICONS" "$APP/Icon.xcassets/AppIcon.appiconset"
printf '{\n  "info": { "author": "xcode", "version": 1 }\n}\n' > "$APP/Icon.xcassets/Contents.json"
