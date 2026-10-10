#!/usr/bin/env bash
# Build scribe-ffi for every app platform and lay the results out for packaging:
#   dist/macos/libscribe_ffi.{a,dylib}            aarch64-apple-darwin
#   dist/ios/libscribe_ffi.a, dist/ios-sim/...     aarch64-apple-ios(-sim) (needs Xcode's iOS SDK)
#   swift/ScribeCore/ScribeFFI.xcframework     macOS + iOS + iOS simulator static libs
#   android/scribe-core/src/main/jniLibs/<abi>/    arm64-v8a, x86_64 (NDK via cargo-ndk)
#   dist/windows/scribe_ffi.dll                    x86_64-pc-windows-gnu (mingw-w64)
# Prints a pass/fail line per target; exits non-zero if any target failed.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/28.2.13676358}"
[ -d /Applications/Xcode.app ] && export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

status=0
result() { printf '%-28s %s\n' "$1" "$2"; [ "$2" = pass ] || status=1; }
build() { cargo build --release -q -p scribe-ffi --target "$1" 2>"dist/logs/$1.log"; }

mkdir -p dist/logs dist/macos dist/ios dist/ios-sim dist/windows

if build aarch64-apple-darwin; then
  cp target/aarch64-apple-darwin/release/libscribe_ffi.{a,dylib} dist/macos/ && result aarch64-apple-darwin pass
else result aarch64-apple-darwin fail; fi

if build aarch64-apple-ios; then
  cp target/aarch64-apple-ios/release/libscribe_ffi.a dist/ios/ && result aarch64-apple-ios pass
else result aarch64-apple-ios fail; fi

if build aarch64-apple-ios-sim; then
  cp target/aarch64-apple-ios-sim/release/libscribe_ffi.a dist/ios-sim/ && result aarch64-apple-ios-sim pass
else result aarch64-apple-ios-sim fail; fi

jni=android/scribe-core/src/main/jniLibs
if cargo ndk -t arm64-v8a -t x86_64 -o "$jni" build --release -q -p scribe-ffi 2>dist/logs/android.log; then
  result "android arm64-v8a+x86_64" pass
else result "android arm64-v8a+x86_64" fail; fi

if build x86_64-pc-windows-gnu; then
  cp target/x86_64-pc-windows-gnu/release/scribe_ffi.dll dist/windows/ && result x86_64-pc-windows-gnu pass
else result x86_64-pc-windows-gnu fail; fi

# XCFramework: static libraries + the UniFFI C header and module map
if [ -f bindings/swift/scribe_ffiFFI.h ]; then
  hdr=dist/xcframework-headers
  rm -rf "$hdr" && mkdir -p "$hdr"
  cp bindings/swift/scribe_ffiFFI.h "$hdr/"
  cp bindings/swift/scribe_ffiFFI.modulemap "$hdr/module.modulemap"
  xcf=swift/ScribeCore/ScribeFFI.xcframework
  rm -rf "$xcf"
  args=(-library dist/macos/libscribe_ffi.a -headers "$hdr")
  [ -f dist/ios/libscribe_ffi.a ] && args+=(-library dist/ios/libscribe_ffi.a -headers "$hdr")
  [ -f dist/ios-sim/libscribe_ffi.a ] && args+=(-library dist/ios-sim/libscribe_ffi.a -headers "$hdr")
  if xcodebuild -create-xcframework "${args[@]}" -output "$xcf" >dist/logs/xcframework.log 2>&1; then
    result xcframework pass
  else result xcframework fail; fi
fi
exit $status
