#!/usr/bin/env bash
# Generate the foreign-language bindings of scribe-ffi into core/bindings/:
#   swift/   UniFFI Swift source + C header + modulemap
#   kotlin/  UniFFI Kotlin source (JNA)
#   c/       C header for the sc_* C ABI (cbindgen)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"

cargo build --release -p scribe-ffi
lib=target/release/libscribe_ffi.dylib
[ -f "$lib" ] || lib=target/release/libscribe_ffi.so

rm -rf bindings/swift bindings/kotlin
cargo run -q --release -p uniffi-bindgen -- generate --library "$lib" --language swift --out-dir bindings/swift
cargo run -q --release -p uniffi-bindgen -- generate --library "$lib" --language kotlin --out-dir bindings/kotlin
mkdir -p bindings/c
cbindgen --config ffi/cbindgen.toml --crate scribe-ffi --output bindings/c/scribe.h ffi

# Wrappers consume the generated sources
mkdir -p swift/ScribeCore/Sources/ScribeCore android/scribe-core/src/main/kotlin/uniffi/scribe_ffi
cp bindings/swift/scribe_ffi.swift swift/ScribeCore/Sources/ScribeCore/
cp bindings/kotlin/uniffi/scribe_ffi/scribe_ffi.kt android/scribe-core/src/main/kotlin/uniffi/scribe_ffi/
ls -R bindings
