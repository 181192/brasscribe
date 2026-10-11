#!/usr/bin/env bash
# Checks built APKs against what the apps promise a phone:
#
#   apps/android/scripts/check-apk.sh app.apk [more.apk ...]
#
# - Android 16 (API 36) is the oldest system the APK installs on, and it targets Android 17 (API 37).
# - Every native library loads on a phone with 16 KB memory pages: its segments are aligned to 16 KB
#   (read with the NDK's llvm-readelf), and it lies uncompressed at a 16 KB offset in the APK (zipalign).
#
# Needs ANDROID_HOME with build-tools, and the NDK or a readelf on PATH. Exits non-zero at the first APK that fails.
set -euo pipefail

SDK="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
MIN_SDK=36
TARGET_SDK=37
PAGE=16384

newest() { find "$SDK/$1" -name "$2" \( -type f -o -type l \) 2>/dev/null | sort -V | tail -1 || true; }
aapt2=$(newest build-tools aapt2)
zipalign=$(newest build-tools zipalign)
# The NDK's llvm-readelf; where there is no NDK (the signing job), the system's llvm-readelf or readelf.
readelf=$(newest ndk llvm-readelf)
[ -n "$readelf" ] || readelf=$(command -v llvm-readelf || command -v readelf || true)
for tool in aapt2 zipalign readelf; do
  [ -n "${!tool}" ] || { echo "check-apk: no $tool under $SDK" >&2; exit 2; }
done
[ $# -gt 0 ] || { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

for apk in "$@"; do
  fail() { echo "check-apk: $apk: $1" >&2; exit 1; }
  badging=$("$aapt2" dump badging "$apk")
  grep -q "^minSdkVersion:'$MIN_SDK'" <<<"$badging" || fail "its floor is not API $MIN_SDK ($(grep '^minSdkVersion' <<<"$badging"))"
  grep -q "^targetSdkVersion:'$TARGET_SDK'" <<<"$badging" || fail "it does not target API $TARGET_SDK ($(grep '^targetSdkVersion' <<<"$badging"))"

  "$zipalign" -c -P 16 4 "$apk" >/dev/null || fail "a native library is not at a 16 KB offset (zipalign -c -P 16 -v 4 shows which)"

  libs=$(mktemp -d)
  # (unzip exits non-zero when nothing matches: an APK without libraries is told so below.)
  unzip -q "$apk" 'lib/*.so' -d "$libs" 2>/dev/null || true
  count=0
  while IFS= read -r so; do
    count=$((count + 1))
    while IFS= read -r align; do
      [ $((align)) -ge $PAGE ] || { rm -rf "$libs"; fail "${so#"$libs"/} has a segment aligned to $align, not 16 KB"; }
    done < <("$readelf" -lW "$so" | awk '$1 == "LOAD" { print $NF }')
  done < <(find "$libs" -name '*.so' | sort)
  rm -rf "$libs"
  [ "$count" -gt 0 ] || fail "it has no native libraries"
  echo "check-apk: $(basename "$apk"): API $MIN_SDK to $TARGET_SDK, $count native libraries aligned to 16 KB"
done
