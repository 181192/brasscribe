#!/usr/bin/env bash
# Prebuilt Rust core artifacts, shared by every checkout and worktree on this machine.
#
#   scripts/core-artifacts.sh ensure [host] [apple] [android]   build once per core change, then copy in
#   scripts/core-artifacts.sh key [component]                   print the cache key
#   scripts/core-artifacts.sh status                            what this checkout has, and what is cached
#   scripts/core-artifacts.sh prune [days]                      drop entries unused for N days (default 14)
#
# Components (default: all whose toolchain is installed):
#   host     core/target/release/libbrasscribe_ffi.{dylib,a} and core/dist/macos/ (JVM, .NET and FFI tests)
#   apple    core/swift/BrasscribeCore/BrasscribeFFI.xcframework (macOS, iOS, iOS simulator)
#   android  apps/android/core-bridge/src/main/jniLibs/{arm64-v8a,x86_64}/libbrasscribe_ffi.so
#
# The key is a hash of the core sources (tracked and untracked, not ignored), Cargo.lock, this
# script, rustc -vV and the component's own toolchain (Xcode, NDK, cargo-ndk). An edit to the core
# makes a new key, so the next ensure rebuilds from this checkout's sources. Entries live in
# $BRASSCRIBE_CACHE/core-artifacts (default ~/.cache/brasscribe). Builds run under a lock on a copy
# of the sources at a fixed path (core-src) with one shared CARGO_TARGET_DIR, so only what changed
# is compiled again.
# Files are copied into the checkout as APFS clones (cp -c): instant, and no extra disk.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/core"
CACHE="${BRASSCRIBE_CACHE:-$HOME/.cache/brasscribe}"
STORE="$CACHE/core-artifacts"
export CARGO_TARGET_DIR="$CACHE/cargo-target/artifacts"
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/28.2.13676358}"
[ -d /Applications/Xcode.app ] && export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
APPLE_ENV="IPHONEOS_DEPLOYMENT_TARGET=18.0 MACOSX_DEPLOYMENT_TARGET=15.0"
STAMPS="$CORE/dist/.artifacts"

log() { printf 'core-artifacts: %s\n' "$*" >&2; }
die() { log "$*"; exit 1; }

hash() { shasum -a 256 | cut -c1-16; }
# clone a file or directory tree (APFS clonefile), falling back to a plain copy
clone() { rm -rf "$2"; mkdir -p "$(dirname "$2")"; cp -cR "$1" "$2" 2>/dev/null || cp -R "$1" "$2"; }

have() {
  case "$1" in
    host) command -v cargo >/dev/null ;;
    apple) [ "$(uname -s)" = Darwin ] && xcrun --find xcodebuild >/dev/null 2>&1 \
      && rustup target list --installed 2>/dev/null | grep -q aarch64-apple-ios-sim ;;
    android) command -v cargo-ndk >/dev/null && [ -d "$ANDROID_NDK_HOME" ] ;;
    *) die "unknown component: $1 (host, apple, android)" ;;
  esac
}

sources() {
  # Everything that goes into the library: the crates' sources and manifests (not their tests),
  # the lock file, the cargo config and the Swift header/modulemap packed into the xcframework.
  git -C "$ROOT" ls-files -co --exclude-standard -z -- \
    core/Cargo.toml core/Cargo.lock core/.cargo \
    core/brasscribe-core core/brasscribe-ffi core/brasscribe-cli core/tools \
    core/bindings/swift/brasscribe_ffiFFI.h core/bindings/swift/brasscribe_ffiFFI.modulemap \
    ':(exclude)core/*/tests/*'
}
sources_hash() { (cd "$ROOT" && sources | xargs -0 shasum -a 256); }

# Builds run on a copy of the sources at one fixed path, $CACHE/core-src. Cargo decides freshness
# by mtime, so building different checkouts into one target dir directly could reuse another
# checkout's objects. rsync -c without -t rewrites only the files whose content differs, with a new
# mtime, and leaves the rest alone: cargo then rebuilds exactly what changed.
sync_sources() {
  local src="$CACHE/core-src"
  mkdir -p "$src"
  (cd "$ROOT" && sources | tr '\0' '\n' | rsync -rc --files-from=- ./ "$src/")
  echo "$src/core"
}

key() {
  local comp="$1"
  {
    sources_hash
    shasum -a 256 "$ROOT/scripts/core-artifacts.sh" | cut -d' ' -f1
    rustc -vV
    case "$comp" in
      apple) xcodebuild -version; echo "$APPLE_ENV" ;;
      android) cargo ndk --version; basename "$ANDROID_NDK_HOME"; echo "api 29" ;;
    esac
  } | hash
}

lock() {
  local l="$STORE/.build.lock" waited=0
  mkdir -p "$STORE"
  until mkdir "$l" 2>/dev/null; do
    local pid; pid=$(cat "$l/pid" 2>/dev/null || true)
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      log "removing stale lock of pid $pid"; rm -rf "$l"; continue
    fi
    [ $waited = 0 ] && log "waiting for the build in progress (pid ${pid:-?})"
    waited=1; sleep 2
  done
  echo $$ > "$l/pid"
  trap 'rm -rf "$STORE/.build.lock"' EXIT
}
unlock() { rm -rf "$STORE/.build.lock"; trap - EXIT; }

build() {
  local comp="$1" out="$2"
  mkdir -p "$out"
  cd "$(sync_sources)"
  case "$comp" in
    host)
      cargo build --release -q --locked -p brasscribe-ffi
      local ext=so; [ "$(uname -s)" = Darwin ] && ext=dylib
      cp "$CARGO_TARGET_DIR/release/libbrasscribe_ffi.$ext" "$CARGO_TARGET_DIR/release/libbrasscribe_ffi.a" "$out/"
      ;;
    apple)
      local t
      for t in aarch64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim; do
        env $APPLE_ENV cargo build --release -q --locked -p brasscribe-ffi --target "$t"
        mkdir -p "$out/lib/$t"; cp "$CARGO_TARGET_DIR/$t/release/libbrasscribe_ffi.a" "$out/lib/$t/"
      done
      local hdr="$out/headers"
      mkdir -p "$hdr"
      cp bindings/swift/brasscribe_ffiFFI.h "$hdr/"
      cp bindings/swift/brasscribe_ffiFFI.modulemap "$hdr/module.modulemap"
      xcodebuild -create-xcframework \
        -library "$out/lib/aarch64-apple-darwin/libbrasscribe_ffi.a" -headers "$hdr" \
        -library "$out/lib/aarch64-apple-ios/libbrasscribe_ffi.a" -headers "$hdr" \
        -library "$out/lib/aarch64-apple-ios-sim/libbrasscribe_ffi.a" -headers "$hdr" \
        -output "$out/BrasscribeFFI.xcframework" >/dev/null
      ;;
    android)
      cargo ndk -t arm64-v8a -t x86_64 -P 29 -o "$out/jniLibs" build --release -q --locked -p brasscribe-ffi
      ;;
  esac
}

# The entry for a component, built if missing. Prints its directory.
entry() {
  local comp="$1" k dir
  k=$(key "$comp")
  dir="$STORE/$comp-$k"
  if [ ! -f "$dir/.complete" ]; then
    lock
    if [ ! -f "$dir/.complete" ]; then
      local tmp="$STORE/.tmp-$comp-$$" s=$SECONDS
      rm -rf "$STORE"/.tmp-*   # left by an interrupted build; only the lock holder builds
      log "building $comp ($k) from $CORE"
      build "$comp" "$tmp"
      touch "$tmp/.complete"
      rm -rf "$dir"; mv "$tmp" "$dir"
      log "built $comp in $((SECONDS - s)) s"
    fi
    unlock
  fi
  touch "$dir/.complete"   # last use, for prune
  echo "$dir"
}

install() {
  local comp="$1" dir="$2" k; k=$(basename "$dir")
  if [ "$(cat "$STAMPS/$comp" 2>/dev/null)" = "$k" ] && installed "$comp"; then
    log "$comp up to date ($k)"; return
  fi
  case "$comp" in
    host)
      local f
      for f in "$dir"/libbrasscribe_ffi.*; do
        clone "$f" "$CORE/target/release/$(basename "$f")"
        [ "$(uname -s)" = Darwin ] && clone "$f" "$CORE/dist/macos/$(basename "$f")"
      done
      ;;
    apple) clone "$dir/BrasscribeFFI.xcframework" "$CORE/swift/BrasscribeCore/BrasscribeFFI.xcframework" ;;
    android)
      local abi
      for abi in arm64-v8a x86_64; do
        clone "$dir/jniLibs/$abi/libbrasscribe_ffi.so" "$ROOT/apps/android/core-bridge/src/main/jniLibs/$abi/libbrasscribe_ffi.so"
      done
      ;;
  esac
  mkdir -p "$STAMPS"; echo "$k" > "$STAMPS/$comp"
  log "$comp installed from $k"
}

installed() {
  case "$1" in
    host) ls "$CORE"/target/release/libbrasscribe_ffi.* >/dev/null 2>&1 ;;
    apple) [ -d "$CORE/swift/BrasscribeCore/BrasscribeFFI.xcframework" ] ;;
    android) [ -f "$ROOT/apps/android/core-bridge/src/main/jniLibs/arm64-v8a/libbrasscribe_ffi.so" ] ;;
  esac
}

components() {
  if [ $# -gt 0 ]; then printf '%s\n' "$@"; return; fi
  local c; for c in host apple android; do have "$c" && echo "$c"; done
}

cmd="${1:-ensure}"; shift || true
case "$cmd" in
  ensure)
    for c in $(components "$@"); do
      have "$c" || die "$c: toolchain not installed"
      install "$c" "$(entry "$c")"
    done
    ;;
  key) for c in $(components "$@"); do echo "$c-$(key "$c")"; done ;;
  status)
    for c in host apple android; do
      if ! have "$c"; then printf '%-8s toolchain not installed\n' "$c"; continue; fi
      k="$c-$(key "$c")"
      printf '%-8s key %s  cached %s  installed %s\n' "$c" "$k" \
        "$([ -f "$STORE/$k/.complete" ] && echo yes || echo no)" \
        "$([ "$(cat "$STAMPS/$c" 2>/dev/null)" = "$k" ] && echo yes || echo no)"
    done
    ;;
  prune)
    days="${1:-14}"
    find "$STORE" -mindepth 1 -maxdepth 1 -type d ! -name '.*' 2>/dev/null | while read -r d; do
      if [ -z "$(find "$d/.complete" -mtime -"$days" 2>/dev/null)" ]; then log "pruning $(basename "$d")"; rm -rf "$d"; fi
    done
    ;;
  *) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
