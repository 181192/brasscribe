#!/usr/bin/env bash
# Puts alphaTab (MPL-2.0, unmodified) into the tab feature's page: the browser build and the Bravura font with its
# licence, from the pinned npm release, checked against its checksum. Nothing is fetched when it is already there.
#   scripts/fetch-alphatab.sh [destination]   default: features/tab/Sources/TabKit/Resources/page/alphatab
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=1.8.4
SHA256=70b2c77abc9698a055d90a11d77308b6b41247936476e969d85770e3d4db4602
DEST="${1:-features/tab/Sources/TabKit/Resources/page/alphatab}"
if [ -f "$DEST/VERSION" ] && [ "$(cat "$DEST/VERSION")" = "$VERSION" ]; then exit 0; fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 -o "$tmp/alphatab.tgz" "https://registry.npmjs.org/@coderline/alphatab/-/alphatab-$VERSION.tgz"
echo "$SHA256  $tmp/alphatab.tgz" | shasum -a 256 -c - >/dev/null
tar -xzf "$tmp/alphatab.tgz" -C "$tmp" package/dist/alphaTab.min.js package/dist/font/Bravura.woff2 \
  package/dist/font/Bravura-OFL.txt package/LICENSE
rm -rf "$DEST"; mkdir -p "$DEST/font"
cp "$tmp/package/dist/alphaTab.min.js" "$DEST/"
cp "$tmp/package/LICENSE" "$DEST/LICENSE.txt"
cp "$tmp/package/dist/font/Bravura.woff2" "$tmp/package/dist/font/Bravura-OFL.txt" "$DEST/font/"
echo "$VERSION" > "$DEST/VERSION"
echo "alphaTab $VERSION in $DEST" >&2
