#!/usr/bin/env bash
# Builds the Rust core's Apple slices (macOS arm64, iOS, iOS simulator) and packs
# core/swift/BrasscribeCore/BrasscribeFFI.xcframework, the same way core/scripts/build-all.sh
# does, without the Android and Windows targets. Output is gitignored by core/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT/core"
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export IPHONEOS_DEPLOYMENT_TARGET=18.0 MACOSX_DEPLOYMENT_TARGET=15.0
mkdir -p dist/macos dist/ios dist/ios-sim
for t in aarch64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim; do
  cargo build --release -q -p brasscribe-ffi --target "$t"
done
cp target/aarch64-apple-darwin/release/libbrasscribe_ffi.a dist/macos/
cp target/aarch64-apple-ios/release/libbrasscribe_ffi.a dist/ios/
cp target/aarch64-apple-ios-sim/release/libbrasscribe_ffi.a dist/ios-sim/
hdr=dist/xcframework-headers
rm -rf "$hdr" && mkdir -p "$hdr"
cp bindings/swift/brasscribe_ffiFFI.h "$hdr/"
cp bindings/swift/brasscribe_ffiFFI.modulemap "$hdr/module.modulemap"
xcf=swift/BrasscribeCore/BrasscribeFFI.xcframework
rm -rf "$xcf"
xcodebuild -create-xcframework \
  -library dist/macos/libbrasscribe_ffi.a -headers "$hdr" \
  -library dist/ios/libbrasscribe_ffi.a -headers "$hdr" \
  -library dist/ios-sim/libbrasscribe_ffi.a -headers "$hdr" \
  -output "$xcf" >/dev/null
echo "built $xcf ($(du -sh "$xcf" | cut -f1))"
