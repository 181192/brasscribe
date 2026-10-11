#!/usr/bin/env bash
# Builds the Rust core's Apple slices (macOS arm64, iOS, iOS simulator) and packs
# core/swift/ScribeCore/ScribeFFI.xcframework, the same way core/scripts/build-all.sh
# does, without the Android and Windows targets. Output is gitignored by core/.
# CORE_SLICES picks the slices when it builds here (default "macos ios ios-sim"): "macos" is enough for the Mac app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# Locally, the shared artifact cache builds once per core change and copies the result in
# (scripts/core-artifacts.sh). CI, or SCRIBE_NO_ARTIFACT_CACHE=1, builds in core/target below.
if [ -z "${CI:-}" ] && [ -z "${SCRIBE_NO_ARTIFACT_CACHE:-}" ]; then exec "$ROOT/scripts/core-artifacts.sh" ensure apple; fi
cd "$ROOT/core"
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export IPHONEOS_DEPLOYMENT_TARGET=18.0 MACOSX_DEPLOYMENT_TARGET=15.0
hdr=dist/xcframework-headers
rm -rf "$hdr" && mkdir -p "$hdr"
cp bindings/swift/scribe_ffiFFI.h "$hdr/"
cp bindings/swift/scribe_ffiFFI.modulemap "$hdr/module.modulemap"
libraries=()
for slice in ${CORE_SLICES:-macos ios ios-sim}; do
  case "$slice" in
    macos) t=aarch64-apple-darwin ;;
    ios) t=aarch64-apple-ios ;;
    ios-sim) t=aarch64-apple-ios-sim ;;
    *) echo "build-core: no slice $slice (macos, ios, ios-sim)" >&2; exit 2 ;;
  esac
  cargo build --release -q -p scribe-ffi --target "$t"
  mkdir -p "dist/$slice"
  cp "target/$t/release/libscribe_ffi.a" "dist/$slice/"
  libraries+=(-library "dist/$slice/libscribe_ffi.a" -headers "$hdr")
done
xcf=swift/ScribeCore/ScribeFFI.xcframework
rm -rf "$xcf"
xcodebuild -create-xcframework "${libraries[@]}" -output "$xcf" >/dev/null
echo "built $xcf ($(du -sh "$xcf" | cut -f1))"
