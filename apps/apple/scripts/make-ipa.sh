#!/usr/bin/env bash
# Builds Brasscribe Play for iPhone and iPad as an unsigned IPA: a Release archive for iOS devices with
# code signing off, packed as Payload/<app>.app. There is no Apple Developer account behind the project,
# so a tester signs the file with their own Apple account (a sideloading tool, or Xcode) to install it.
#
# Usage: scripts/make-ipa.sh [out.ipa]     (default build/brasscribe-play-ios-unsigned.ipa)
# Needs what `make project` needs (Verovio and the core with their iOS device slices), and the phone
# band SoundFont in data/sounds/band unless IPA_ALLOW_NO_BAND_SOUNDS=1 (a local try-out; never a release).
#
# The file is checked before it is kept: one app for iPhone and iPad, the texts iOS shows when it asks
# for the microphone and the local network, every binary built for iOS devices on arm64 (not the
# simulator), and no signature or provisioning profile left inside.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
OUT="${1:-$HERE/build/brasscribe-play-ios-unsigned.ipa}"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
WORK="$HERE/build/ipa"
fail() { echo "error: $*" >&2; exit 1; }

xcodegen generate
rm -rf "$WORK"; mkdir -p "$WORK/Payload" "$(dirname "$OUT")"
xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath build/DerivedData \
  -scheme BrasscribePlay-iOS -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$WORK/BrasscribePlay.xcarchive" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" archive

built=$(find "$WORK/BrasscribePlay.xcarchive/Products/Applications" -maxdepth 1 -name '*.app' | head -1)
[ -n "$built" ] || fail "the archive holds no .app"
ditto "$built" "$WORK/Payload/$(basename "$built")"
app="$WORK/Payload/$(basename "$built")"
plist="$app/Info.plist"

value() { plutil -extract "$1" raw -o - "$plist" 2>/dev/null || true; }
json() { plutil -extract "$1" json -o - "$plist" 2>/dev/null || true; }

id=$(value CFBundleIdentifier); version=$(value CFBundleShortVersionString); build=$(value CFBundleVersion)
[ -n "$id" ] && [ -n "$version" ] && [ -n "$build" ] || fail "Info.plist has no bundle id or version"
family=$(json UIDeviceFamily)
[ "$family" = "[1,2]" ] || fail "UIDeviceFamily is ${family:-missing}, expected [1,2] (iPhone and iPad)"
for key in NSMicrophoneUsageDescription NSLocalNetworkUsageDescription NSCameraUsageDescription; do
  [ -n "$(value "$key")" ] || fail "Info.plist has no $key"
done
json NSBonjourServices | grep -q '"_brasscribe._tcp"' || fail "NSBonjourServices does not list _brasscribe._tcp"
json CFBundleURLTypes | grep -q '"brasscribe"' || fail "the brasscribe: address for pairing is not declared"

# lipo cannot tell a device binary from a simulator one (both are arm64): the build version's platform can.
binaries=("$app/$(value CFBundleExecutable)")
while IFS= read -r fw; do binaries+=("$fw/$(basename "$fw" .framework)"); done \
  < <(find "$app/Frameworks" -maxdepth 1 -name '*.framework' 2>/dev/null)
while IFS= read -r lib; do binaries+=("$lib"); done \
  < <(find "$app" -name '*.dylib' 2>/dev/null)
for bin in "${binaries[@]}"; do
  [ -f "$bin" ] || fail "no binary at ${bin#"$WORK/"}"
  archs=$(lipo -archs "$bin")
  [ "$archs" = arm64 ] || fail "${bin#"$WORK/"} is built for '$archs', expected arm64 only"
  platform=$(xcrun vtool -show-build "$bin" | awk '$1 == "platform" { print $2 }' | sort -u | tr '\n' ' ')
  [ "$platform" = "IOS " ] || fail "${bin#"$WORK/"} is built for platform '$platform', expected IOS (a device)"
  echo "ok: ${bin#"$WORK/Payload/"} (arm64, iOS device)"
done

signed=$(find "$app" \( -name _CodeSignature -o -name embedded.mobileprovision -o -name '*.entitlements' \) -print)
[ -z "$signed" ] || fail "signing leftovers in the app: $signed"

if [ -s "$app/Sounds/brasscribe-band-mobile.sf2" ] && [ -s "$app/Sounds/mapping.json" ]; then
  echo "ok: band sounds ($(du -h "$app/Sounds/brasscribe-band-mobile.sf2" | cut -f1))"
elif [ -n "${IPA_ALLOW_NO_BAND_SOUNDS:-}" ]; then
  echo "warning: no band SoundFont in the app; it will play the basic tier" >&2
else
  fail "the app has no band SoundFont (pixi run fetch-sounds, or IPA_ALLOW_NO_BAND_SOUNDS=1 for a try-out)"
fi
[ -d "$app/VerovioResources" ] || fail "the app has no VerovioResources (notation fonts)"

# zip, not ditto: no resource forks or __MACOSX entries; -y keeps symlinks as they are.
rm -f "$OUT"
(cd "$WORK" && zip -qry "$OUT" Payload)
echo "built $OUT: $id $version ($build), app $(du -sh "$app" | cut -f1), ipa $(du -h "$OUT" | cut -f1)"
