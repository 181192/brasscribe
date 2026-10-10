#!/usr/bin/env bash
# Builds the Rust core's Apple slices (macOS arm64, iOS, iOS simulator) and packs
# core/swift/ScribeCore/ScribeFFI.xcframework, the same way core/scripts/build-all.sh
# does, without the Android and Windows targets. Output is gitignored by core/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# Locally, the shared artifact cache builds once per core change and copies the result in
# (scripts/core-artifacts.sh). CI, or SCRIBE_NO_ARTIFACT_CACHE=1, builds in core/target below.
if [ -z "${CI:-}" ] && [ -z "${SCRIBE_NO_ARTIFACT_CACHE:-}" ]; then exec "$ROOT/scripts/core-artifacts.sh" ensure apple; fi
cd "$ROOT/core"
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export IPHONEOS_DEPLOYMENT_TARGET=18.0 MACOSX_DEPLOYMENT_TARGET=15.0
mkdir -p dist/macos dist/ios dist/ios-sim
for t in aarch64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim; do
  cargo build --release -q -p scribe-ffi --target "$t"
done
cp target/aarch64-apple-darwin/release/libscribe_ffi.a dist/macos/
cp target/aarch64-apple-ios/release/libscribe_ffi.a dist/ios/
cp target/aarch64-apple-ios-sim/release/libscribe_ffi.a dist/ios-sim/
hdr=dist/xcframework-headers
rm -rf "$hdr" && mkdir -p "$hdr"
cp bindings/swift/scribe_ffiFFI.h "$hdr/"
cp bindings/swift/scribe_ffiFFI.modulemap "$hdr/module.modulemap"
xcf=swift/ScribeCore/ScribeFFI.xcframework
rm -rf "$xcf"
xcodebuild -create-xcframework \
  -library dist/macos/libscribe_ffi.a -headers "$hdr" \
  -library dist/ios/libscribe_ffi.a -headers "$hdr" \
  -library dist/ios-sim/libscribe_ffi.a -headers "$hdr" \
  -output "$xcf" >/dev/null
echo "built $xcf ($(du -sh "$xcf" | cut -f1))"
