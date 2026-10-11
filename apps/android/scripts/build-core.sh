#!/bin/bash
# Builds the Rust core's Android libraries (libscribe_ffi.so for arm64-v8a and x86_64) with
# cargo-ndk into apps/android/core-bridge/src/main/jniLibs (git-ignored), and copies the UniFFI
# Kotlin bindings from core/android. Without the libraries the app runs on the Kotlin fallback.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
core="$(cd "$here/../../core" && pwd)"
# Locally, the shared artifact cache builds once per core change and copies the result in
# (scripts/core-artifacts.sh). CI, or SCRIBE_NO_ARTIFACT_CACHE=1, builds in core/target below.
if [ -z "${CI:-}" ] && [ -z "${SCRIBE_NO_ARTIFACT_CACHE:-}" ]; then exec "$here/../../scripts/core-artifacts.sh" ensure android; fi
export PATH=/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/28.2.13676358}"
out="$here/core-bridge/src/main/jniLibs"
mkdir -p "$out"
(cd "$core" && cargo ndk -t arm64-v8a -t x86_64 -P 29 -o "$out" build --release -q -p scribe-ffi)
ls -l "$out"/*/libscribe_ffi.so
