#!/usr/bin/env bash
# Prebuilt Rust core artifacts, shared by every checkout and worktree on this machine.
#
#   scripts/core-artifacts.sh ensure [host] [apple] [android]   build once per core change, then copy in
#   scripts/core-artifacts.sh key [component]                   print the cache key
#   scripts/core-artifacts.sh status                            what this checkout has, and what is cached
#   scripts/core-artifacts.sh prune [days]                      drop entries unused for N days (default 14)
#
# Components (default: all whose toolchain is installed):
#   host     core/target/release/libscribe_ffi.{dylib,a} and core/dist/macos/ (JVM, .NET and FFI tests),
#            and the command line core/target/release/scribe-core (the engine's bass-tab profile)
#   apple    core/swift/ScribeCore/ScribeFFI.xcframework (macOS, iOS, iOS simulator)
#   android  apps/android/core-bridge/src/main/jniLibs/{arm64-v8a,x86_64}/libscribe_ffi.so
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

# The `members = [...]` of the core workspace, as paths from the repository root.
workspace_members() {
  awk '/^members[[:space:]]*=/{on=1} on{print} on&&/\]/{exit}' "$ROOT/core/Cargo.toml" \
    | grep -oE '"[^"]+"' | tr -d '"' | sed 's|^|core/|'
}

sources() {
  # Everything that goes into the library: the crates' sources and manifests (not their tests),
  # the lock file, the cargo config and the Swift header/modulemap packed into the xcframework.
  # A tracked file deleted in the working tree is still listed by git, but is not a source.
  # The crates are the workspace's members, read from core/Cargo.toml, so a new member is a source
  # without a change here (cargo refuses a workspace with a member missing).
  local members
  members=$(workspace_members) || members=""
  [ -n "$members" ] || { echo "core-artifacts: no workspace members found in core/Cargo.toml" >&2; return 1; }
  # shellcheck disable=SC2086  # one path per member; member paths have no spaces
  git -C "$ROOT" ls-files -co --exclude-standard -z -- \
    core/Cargo.toml core/Cargo.lock core/.cargo \
    $members \
    core/bindings/swift/scribe_ffiFFI.h core/bindings/swift/scribe_ffiFFI.modulemap \
    ':(exclude)core/*/tests/*' ':(exclude)core/targets/*/tests/*' \
    | while IFS= read -r -d '' f; do [ -e "$ROOT/$f" ] && printf '%s\0' "$f"; done
}
sources_hash() { (cd "$ROOT" && sources | xargs -0 shasum -a 256); }

# Builds run on a copy of the sources at one fixed path, $CACHE/core-src. Cargo decides freshness
# by mtime, so building different checkouts into one target dir directly could reuse another
# checkout's objects. rsync -c without -t rewrites only the files whose content differs, with a new
# mtime, and leaves the rest alone: cargo then rebuilds exactly what changed. rsync --files-from
# never deletes, so files that are not sources of this checkout (deleted here, or left by another
# checkout) are removed afterwards: the copy holds exactly this checkout's sources.
sync_sources() {
  local src="$CACHE/core-src" list
  mkdir -p "$src" || return 1
  list=$(sources | tr '\0' '\n' | LC_ALL=C sort) || return 1
  [ -n "$list" ] || return 1
  printf '%s\n' "$list" | rsync -rc --files-from=- "$ROOT/" "$src/" || return 1
  (cd "$src" && find . -type f | sed 's|^\./||' | LC_ALL=C sort | LC_ALL=C comm -23 - <(printf '%s\n' "$list") \
    | while IFS= read -r f; do rm -f "$f"; done && find . -mindepth 1 -type d -empty -delete) || return 1
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

# Called as a condition, where set -e does not apply, so every step checks its own status: a failed
# cargo build must not go on to copy the previous build's library out of the shared target directory.
build() {
  local comp="$1" out="$2" src
  mkdir -p "$out" || return 1
  src=$(sync_sources) || { log "copying the sources to $CACHE/core-src failed"; return 1; }
  cd "$src" || return 1
  case "$comp" in
    host)
      cargo build --release -q --locked -p scribe-ffi || return 1
      local ext=so; [ "$(uname -s)" = Darwin ] && ext=dylib
      cp "$CARGO_TARGET_DIR/release/libscribe_ffi.$ext" "$CARGO_TARGET_DIR/release/libscribe_ffi.a" "$out/" || return 1
      # On its own, so the library is built with the same features as before the command line was added.
      cargo build --release -q --locked -p scribe-cli || return 1
      cp "$CARGO_TARGET_DIR/release/scribe-core" "$out/" || return 1
      ;;
    apple)
      local t
      for t in aarch64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim; do
        env $APPLE_ENV cargo build --release -q --locked -p scribe-ffi --target "$t" || return 1
        mkdir -p "$out/lib/$t" && cp "$CARGO_TARGET_DIR/$t/release/libscribe_ffi.a" "$out/lib/$t/" || return 1
      done
      local hdr="$out/headers"
      mkdir -p "$hdr" || return 1
      cp bindings/swift/scribe_ffiFFI.h "$hdr/" || return 1
      cp bindings/swift/scribe_ffiFFI.modulemap "$hdr/module.modulemap" || return 1
      xcodebuild -create-xcframework \
        -library "$out/lib/aarch64-apple-darwin/libscribe_ffi.a" -headers "$hdr" \
        -library "$out/lib/aarch64-apple-ios/libscribe_ffi.a" -headers "$hdr" \
        -library "$out/lib/aarch64-apple-ios-sim/libscribe_ffi.a" -headers "$hdr" \
        -output "$out/ScribeFFI.xcframework" >/dev/null || return 1
      ;;
    android)
      cargo ndk -t arm64-v8a -t x86_64 -P 29 -o "$out/jniLibs" build --release -q --locked -p scribe-ffi || return 1
      ;;
  esac
}

# Whether an entry holds every file of its component.
built() {
  local d="$2"
  case "$1" in
    host) [ -f "$d/libscribe_ffi.a" ] && { [ -f "$d/libscribe_ffi.so" ] || [ -f "$d/libscribe_ffi.dylib" ]; } \
      && [ -x "$d/scribe-core" ] ;;
    apple) [ -f "$d/ScribeFFI.xcframework/Info.plist" ] ;;
    android) [ -f "$d/jniLibs/arm64-v8a/libscribe_ffi.so" ] && [ -f "$d/jniLibs/x86_64/libscribe_ffi.so" ] ;;
  esac
}

# The entry for a component, built if missing or incomplete. Prints its directory. It runs in a
# command substitution, where set -e does not apply: failures exit explicitly.
entry() {
  local comp="$1" k dir
  k=$(key "$comp") || die "$comp: computing the cache key failed"
  dir="$STORE/$comp-$k"
  if [ ! -f "$dir/.complete" ] || ! built "$comp" "$dir"; then
    lock
    if [ ! -f "$dir/.complete" ] || ! built "$comp" "$dir"; then
      local tmp="$STORE/.tmp-$comp-$$" s=$SECONDS
      rm -rf "$STORE"/.tmp-*   # left by an interrupted build; only the lock holder builds
      log "building $comp ($k) from $CORE"
      if ! build "$comp" "$tmp" || ! built "$comp" "$tmp"; then
        rm -rf "$tmp"; unlock; die "build of $comp failed; nothing was cached or installed"
      fi
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
      for f in "$dir"/libscribe_ffi.*; do
        clone "$f" "$CORE/target/release/$(basename "$f")"
        [ "$(uname -s)" = Darwin ] && clone "$f" "$CORE/dist/macos/$(basename "$f")"
      done
      clone "$dir/scribe-core" "$CORE/target/release/scribe-core"
      ;;
    apple) clone "$dir/ScribeFFI.xcframework" "$CORE/swift/ScribeCore/ScribeFFI.xcframework" ;;
    android)
      local abi
      for abi in arm64-v8a x86_64; do
        clone "$dir/jniLibs/$abi/libscribe_ffi.so" "$ROOT/apps/android/core-bridge/src/main/jniLibs/$abi/libscribe_ffi.so"
      done
      ;;
  esac
  mkdir -p "$STAMPS"; echo "$k" > "$STAMPS/$comp"
  log "$comp installed from $k"
}

installed() {
  case "$1" in
    host) ls "$CORE"/target/release/libscribe_ffi.* >/dev/null 2>&1 && [ -x "$CORE/target/release/scribe-core" ] ;;
    apple) [ -d "$CORE/swift/ScribeCore/ScribeFFI.xcframework" ] ;;
    android) [ -f "$ROOT/apps/android/core-bridge/src/main/jniLibs/arm64-v8a/libscribe_ffi.so" ] ;;
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
      dir=$(entry "$c") || exit 1
      install "$c" "$dir"
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
