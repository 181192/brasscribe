#!/usr/bin/env bash
# Compile the generated Kotlin bindings with a smoke test and run them on the
# JVM against the macOS library (JNA). Usage: run.sh [path/to/jna.jar]
set -euo pipefail
cd "$(dirname "$0")/../.."
jna="${1:-${JNA_JAR:-}}"
if [ -z "$jna" ]; then
  jna=target/jna-5.17.0.jar
  [ -f "$jna" ] || curl -sfL -o "$jna" https://repo1.maven.org/maven2/net/java/dev/jna/jna/5.17.0/jna-5.17.0.jar
fi
out=target/kotlin-smoke
mkdir -p "$out"
kotlinc -cp "$jna" bindings/kotlin/uniffi/brasscribe_ffi/brasscribe_ffi.kt android/smoke/Smoke.kt -include-runtime -d "$out/smoke.jar" 2>&1 | grep -v "^warning" || true
java --enable-native-access=ALL-UNNAMED -Djna.library.path=dist/macos -cp "$out/smoke.jar:$jna" SmokeKt
