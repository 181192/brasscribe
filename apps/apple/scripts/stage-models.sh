#!/usr/bin/env bash
# Stage the on-device models for the app bundles: apps/apple/products/brasscribe/Models/<platform>/Models/
# (not committed) becomes each bundle's Models/ folder, where OnDeviceKit looks for them first (ModelStore),
# with NOTICE.md beside them: each model's source and licence (convert/on-device-models-NOTICE.md).
# Each Core ML package is compiled here, for its platform, so the app loads it as it is: nothing is
# downloaded, and no package is compiled on the device.
# The same three for macOS and iOS, devices and simulators: SwiftF0, Basic Pitch and Beat This small0, all fp32.
# The packages come from models/converted (`python3 convert/models_pack.py fetch`, or a conversion of
# your own: convert/README.md). Run by `make models` and by check-prereqs.sh before the project is
# generated. Without them that platform's folder stays empty and the app makes its scores on the computer.
# Packages that are there must be the pinned ones (convert/on-device-models.json), or the script stops:
# an app is not built from a conversion nobody pinned. SCRIBE_ALLOW_UNPINNED_MODELS=1 lets a conversion
# of your own through, for a local try-out; never a release.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CONVERTED="${SCRIBE_MODELS:-$ROOT/models/converted}"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
OS_MIN=26.0   # the deployment targets in products/brasscribe/project.yml

MODELS="swift-f0/swift-f0-window-fp32 basic-pitch/nmp-b1-fp32 beat-this/beat-this-small0-fp32"

# The packages that are there, against the pin.
pinned=()
for m in $MODELS; do [ -d "$CONVERTED/$m.mlpackage" ] && pinned+=("$(basename "$m").mlpackage.zip"); done
if [ "${#pinned[@]}" -gt 0 ] && ! python3 "$ROOT/convert/models_pack.py" verify --dir "$CONVERTED" "${pinned[@]}" >/dev/null; then
  if [ -n "${SCRIBE_ALLOW_UNPINNED_MODELS:-}" ]; then
    echo "warning: the models in $CONVERTED are not the pinned ones; staging them because SCRIBE_ALLOW_UNPINNED_MODELS is set." >&2
  else
    echo "error: the models in $CONVERTED are not the ones pinned in convert/on-device-models.json." \
         "Run: python3 convert/models_pack.py fetch (or SCRIBE_ALLOW_UNPINNED_MODELS=1 to try a conversion of your own)." >&2
    exit 1
  fi
fi

compile() {  # <platform> <coremlcompiler platform> <folder/package name>; fails when the package is not there
  local platform="$1" target="$2" m="$3"
  local out="$HERE/products/brasscribe/Models/$platform/Models" stamps="$HERE/products/brasscribe/Models/$platform/stamps"
  local src="$CONVERTED/$m.mlpackage" name; name="$(basename "$m")"
  local dst="$out/$name.mlmodelc" stamp="$stamps/$name"
  mkdir -p "$out" "$stamps"
  if [ ! -d "$src" ]; then rm -rf "$dst" "$stamp"; return 1; fi
  # compiled again only when the package changed
  local sum; sum="$(cd "$src" && find . -type f -exec shasum -a 256 {} + | sort | shasum -a 256 | cut -d' ' -f1)"
  if [ -d "$dst" ] && [ "$(cat "$stamp" 2>/dev/null)" = "$sum" ]; then return 0; fi
  rm -rf "$dst"
  xcrun coremlcompiler compile "$src" "$out" --platform "$target" --deployment-target "$OS_MIN" >/dev/null
  [ -d "$dst" ] || { echo "error: $src did not compile to $dst" >&2; exit 1; }
  echo "$sum" > "$stamp"
  echo "model staged for $platform: $name ($(du -sh "$dst" | cut -f1))"
}

stage() {  # <platform> <coremlcompiler platform>: the three models
  local platform="$1" target="$2" missing=""
  for m in $MODELS; do
    compile "$platform" "$target" "$m" || missing="$missing $m.mlpackage"
  done
  # the models' sources and licences travel with them (Basic Pitch's Apache-2.0 notice among them)
  local out="$HERE/products/brasscribe/Models/$platform/Models"
  if ls "$out"/*.mlmodelc >/dev/null 2>&1; then cp "$ROOT/convert/on-device-models-NOTICE.md" "$out/NOTICE.md"; else rm -f "$out/NOTICE.md"; fi
  if [ -n "$missing" ]; then
    echo "warning: not in $CONVERTED:$missing (run: python3 convert/models_pack.py fetch); the $platform app" \
         "will make its scores on the computer." >&2
  fi
}

stage macOS macos
stage iOS ios
