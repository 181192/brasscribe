#!/usr/bin/env bash
# Run before generating the Xcode project: the Verovio framework is built locally.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -d "$HERE/Frameworks/Verovio.xcframework" ] || [ ! -d "$HERE/Frameworks/VerovioResources" ]; then
  echo "error: Verovio.xcframework missing. Run apps/apple/scripts/build-verovio.sh first." >&2
  exit 1
fi
if [ ! -d "$HERE/../../core/swift/BrasscribeCore/BrasscribeFFI.xcframework" ]; then
  echo "error: BrasscribeFFI.xcframework missing. Run apps/apple/scripts/build-core.sh first." >&2
  exit 1
fi
# actool does not follow symlinks inside a catalog, so the app icon set from
# design/dist is copied into a generated catalog (App/Icon.xcassets, not committed).
ICONS="$HERE/../../design/dist/icons/apple/AppIcon.appiconset"
mkdir -p "$HERE/App/Icon.xcassets"
rm -rf "$HERE/App/Icon.xcassets/AppIcon.appiconset"
cp -R "$ICONS" "$HERE/App/Icon.xcassets/AppIcon.appiconset"
printf '{\n  "info": { "author": "xcode", "version": 1 }\n}\n' > "$HERE/App/Icon.xcassets/Contents.json"
