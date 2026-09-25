#!/usr/bin/env bash
# Generate the foreign-language bindings of brasscribe-ffi into core/bindings/:
#   swift/   UniFFI Swift source + C header + modulemap
#   kotlin/  UniFFI Kotlin source (JNA)
#   c/       C header for the bc_* C ABI (cbindgen)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"

cargo build --release -p brasscribe-ffi
lib=target/release/libbrasscribe_ffi.dylib
[ -f "$lib" ] || lib=target/release/libbrasscribe_ffi.so

rm -rf bindings/swift bindings/kotlin
cargo run -q --release -p uniffi-bindgen -- generate --library "$lib" --language swift --out-dir bindings/swift
cargo run -q --release -p uniffi-bindgen -- generate --library "$lib" --language kotlin --out-dir bindings/kotlin
mkdir -p bindings/c
cbindgen --config brasscribe-ffi/cbindgen.toml --crate brasscribe-ffi --output bindings/c/brasscribe.h brasscribe-ffi

# Wrappers consume the generated sources
mkdir -p swift/BrasscribeCore/Sources/BrasscribeCore android/brasscribe-core/src/main/kotlin/uniffi/brasscribe_ffi
cp bindings/swift/brasscribe_ffi.swift swift/BrasscribeCore/Sources/BrasscribeCore/
cp bindings/kotlin/uniffi/brasscribe_ffi/brasscribe_ffi.kt android/brasscribe-core/src/main/kotlin/uniffi/brasscribe_ffi/
ls -R bindings
