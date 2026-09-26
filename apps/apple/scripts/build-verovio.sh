#!/usr/bin/env bash
# Builds Verovio (LGPL-3.0, unmodified upstream source) as a dynamic framework for
# macOS, iOS and the iOS simulator, and packs the slices into Verovio.xcframework.
#
# Output (gitignored): apps/apple/Frameworks/Verovio.xcframework
#                      apps/apple/Frameworks/VerovioResources/  (font subset loaded at runtime)
#
# Env: VEROVIO_HUMDRUM=1 keeps Humdrum support (bigger binary; not needed for MusicXML).
set -euo pipefail

VERSION=6.3.0
COMMIT=425dd7b6ba26edcecbe345c10b15586d095743d9
MACOS_MIN=15.0
IOS_MIN=18.0

HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$HERE/build/verovio"
SRC="$WORK/src"
OUT="$HERE/Frameworks"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
JOBS="${JOBS:-$(sysctl -n hw.ncpu)}"
HUMDRUM="${VEROVIO_HUMDRUM:-0}"

mkdir -p "$WORK" "$OUT"
if [ ! -d "$SRC/.git" ]; then
  git clone --quiet --depth 1 --branch "version-$VERSION" https://github.com/rism-digital/verovio "$SRC"
fi
got="$(git -C "$SRC" rev-parse HEAD)"
[ "$got" = "$COMMIT" ] || { echo "verovio checkout is $got, expected $COMMIT" >&2; exit 1; }
[ -z "$(git -C "$SRC" status --porcelain)" ] || { echo "verovio source tree is modified" >&2; exit 1; }

no_hum=ON; [ "$HUMDRUM" = 1 ] && no_hum=OFF

# build_slice <name> <Darwin|iOS> <sysroot> <archs> <min os>
build_slice() {
  local name=$1 system=$2 sysroot=$3 archs=$4 minos=$5
  local b="$WORK/build-$name"
  local extra=()
  [ "$system" = iOS ] && extra+=(-DCMAKE_SYSTEM_NAME=iOS)
  cmake -S "$SRC/cmake" -B "$b" -G "Unix Makefiles" \
    "${extra[@]}" \
    -DCMAKE_BUILD_TYPE=MinSizeRel \
    -DCMAKE_OSX_SYSROOT="$sysroot" \
    -DCMAKE_OSX_ARCHITECTURES="$archs" \
    -DCMAKE_OSX_DEPLOYMENT_TARGET="$minos" \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-dead_strip" \
    -DBUILD_AS_LIBRARY=ON -DNO_HUMDRUM_SUPPORT=$no_hum >"$b.cmake.log" 2>&1 \
    || { cat "$b.cmake.log"; return 1; }
  make -C "$b" -j"$JOBS" verovio >"$b.make.log" 2>&1 || { tail -40 "$b.make.log"; return 1; }
  local dylib; dylib="$(find "$b" -maxdepth 1 -name 'libverovio*.dylib' -type f | head -1)"
  [ -n "$dylib" ] || { echo "no dylib in $b" >&2; return 1; }

  local fw="$WORK/fw-$name/Verovio.framework"
  rm -rf "$WORK/fw-$name"; mkdir -p "$WORK/fw-$name"
  local root res bin minkey=MinimumOSVersion
  if [ "$system" = Darwin ]; then
    mkdir -p "$fw/Versions/A/Headers" "$fw/Versions/A/Modules" "$fw/Versions/A/Resources"
    root="$fw/Versions/A"; res="$root/Resources"; bin="$root/Verovio"; minkey=LSMinimumSystemVersion
  else
    mkdir -p "$fw/Headers" "$fw/Modules"
    root="$fw"; res="$fw"; bin="$fw/Verovio"
  fi
  cp "$dylib" "$bin"
  strip -x "$bin"
  install_name_tool -id @rpath/Verovio.framework/Verovio "$bin"
  cp "$SRC/tools/c_wrapper.h" "$root/Headers/c_wrapper.h"
  printf '#include <stdbool.h>\n#include "c_wrapper.h"\n' > "$root/Headers/Verovio.h"
  printf 'framework module Verovio {\n    umbrella header "Verovio.h"\n    export *\n}\n' > "$root/Modules/module.modulemap"
  cat > "$res/Info.plist" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>Verovio</string>
  <key>CFBundleIdentifier</key><string>org.verovio.Verovio</string>
  <key>CFBundleName</key><string>Verovio</string>
  <key>CFBundlePackageType</key><string>FMWK</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>$minkey</key><string>$minos</string>
</dict></plist>
P
  if [ "$system" = Darwin ]; then
    ln -sfn A "$fw/Versions/Current"
    for l in Verovio Headers Modules Resources; do ln -sfn "Versions/Current/$l" "$fw/$l"; done
  fi
  echo "slice $name: $(du -sh "$bin" | cut -f1) ($(lipo -archs "$bin"))"
}

build_slice macos Darwin macosx "arm64;x86_64" $MACOS_MIN &
p1=$!
build_slice ios iOS iphoneos arm64 $IOS_MIN &
p2=$!
build_slice ios-sim iOS iphonesimulator arm64 $IOS_MIN &
p3=$!
wait $p1; wait $p2; wait $p3

rm -rf "$OUT/Verovio.xcframework"
xcodebuild -create-xcframework \
  -framework "$WORK/fw-macos/Verovio.framework" \
  -framework "$WORK/fw-ios/Verovio.framework" \
  -framework "$WORK/fw-ios-sim/Verovio.framework" \
  -output "$OUT/Verovio.xcframework" >/dev/null

# Runtime resources: the two SMuFL fonts the app uses plus text metrics.
R="$OUT/VerovioResources"
rm -rf "$R"; mkdir -p "$R"
for f in Leipzig Bravura; do cp -R "$SRC/data/$f" "$R/"; cp "$SRC/data/$f.xml" "$SRC/data/$f.css" "$R/"; done
cp -R "$SRC/data/text" "$R/"
cp "$SRC/COPYING" "$SRC/COPYING.LESSER" "$OUT/"
# the LGPL text ships inside the app with the font data
cp "$SRC/COPYING" "$SRC/COPYING.LESSER" "$R/"
echo "$VERSION $COMMIT humdrum=$HUMDRUM" > "$OUT/VEROVIO_VERSION"
echo "done: $OUT/Verovio.xcframework ($(du -sh "$OUT/Verovio.xcframework" | cut -f1)), resources $(du -sh "$R" | cut -f1)"
