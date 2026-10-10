#!/bin/bash
# Reduced-operator ONNX Runtime 1.30.0 for Android (arm64-v8a, x86_64), with only the kernels that
# SwiftF0 (window), Basic Pitch (nmp-b1) and Beat This! small0 need, their ORT-optimized graphs
# included (ops.config, made with tools/python/create_reduced_build_config.py). It still loads
# .onnx files and has the same ai.onnxruntime Java API as com.microsoft.onnxruntime:onnxruntime-android.
# Output: apps/android/third_party/onnxruntime/onnxruntime-android-reduced.aar (git-ignored), which the
# app uses instead of the Maven AAR when present. Needs JDK 17 for ORT's Java build (JAVA_HOME).
#   usage: build-reduced-ort.sh <work dir>
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="${1:?work dir}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT=$ANDROID_HOME
mkdir -p "$work"
[ -d "$work/ort" ] || git clone --depth 1 -b v1.30.0 https://github.com/microsoft/onnxruntime.git "$work/ort"
cd "$work/ort"
for abi in arm64-v8a x86_64; do
  python tools/ci_build/build.py --build_dir "$work/build-$abi" --config MinSizeRel \
    --android --android_sdk_path "$ANDROID_HOME" --android_ndk_path "$ANDROID_HOME/ndk/28.2.13676358" \
    --android_abi "$abi" --android_api 29 \
    --build_java --build_shared_lib --include_ops_by_config "$here/ops.config" --disable_ml_ops \
    --skip_tests --parallel --compile_no_warning_as_error --skip_submodule_sync \
    --cmake_extra_defines onnxruntime_BUILD_UNIT_TESTS=OFF
done
# Each ABI build writes a release AAR with only its own jni/<abi>; merge the second ABI's native
# libraries into the first one's AAR.
aar_of() { echo "$work/build-$1/MinSizeRel/java/build/android/outputs/aar/onnxruntime-release.aar"; }
merge="$work/aar"
rm -rf "$merge" && mkdir -p "$merge"
(cd "$merge" && unzip -q "$(aar_of arm64-v8a)" && unzip -q -o "$(aar_of x86_64)" 'jni/*')
out="$here/../../third_party/onnxruntime"
mkdir -p "$out"
rm -f "$out/onnxruntime-android-reduced.aar"
(cd "$merge" && zip -q -r -X "$out/onnxruntime-android-reduced.aar" .)
unzip -l "$out/onnxruntime-android-reduced.aar" | grep 'libonnxruntime.so'
