#!/bin/sh
# Build sfizz_render (sfizz 1.2.3, BSD-2-Clause) into data/sounds/tools/bin/.
# Homebrew has no sfizz formula; this builds the release tarball with a pip-provided CMake.
# Two fixes are needed with Apple clang on arm64: sfizz's CMake adds 32-bit ARM flags
# (-mfpu=neon -mfloat-abi=hard) for any "arm*" processor, and atomic_queue trips a
# newer clang diagnostic.
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
work="$root/data/sounds/tools/sfizz-src"
ver=1.2.3
mkdir -p "$work" "$root/data/sounds/tools/bin"
cd "$work"
[ -d "sfizz-$ver" ] || { curl -sL -o src.tar.gz "https://github.com/sfztools/sfizz/releases/download/$ver/sfizz-$ver.tar.gz"; tar xzf src.tar.gz; }
python3 - "sfizz-$ver/cmake/SfizzConfig.cmake" <<'PY'
import sys; p = sys.argv[1]; s = open(p).read()
open(p, "w").write(s.replace('MATCHES "(arm.*)"', 'MATCHES "^(armv7.*|arm)$"'))
PY
cmake="uv tool run --from cmake cmake"
$cmake -S "sfizz-$ver" -B build -DCMAKE_BUILD_TYPE=Release -DSFIZZ_JACK=OFF -DSFIZZ_RENDER=ON -DSFIZZ_SHARED=OFF \
  -DSFIZZ_TESTS=OFF -DSFIZZ_BENCHMARKS=OFF -DSFIZZ_DEMOS=OFF -DSFIZZ_DEVTOOLS=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  "-DCMAKE_CXX_FLAGS=-Wno-missing-template-arg-list-after-template-kw" >/dev/null
$cmake --build build -j 8 --target sfizz_render >/dev/null
cp build/library/bin/sfizz_render "$root/data/sounds/tools/bin/sfizz_render"
echo "$root/data/sounds/tools/bin/sfizz_render"
