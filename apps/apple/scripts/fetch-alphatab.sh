#!/usr/bin/env bash
# Puts alphaTab (MPL-2.0, unmodified) into the tab feature's page: the browser build and the Bravura font with its
# licence, from the pinned npm release, checked against its checksum. Nothing is fetched when it is already there.
#   scripts/fetch-alphatab.sh [destination]   default: features/tab/Sources/TabKit/Resources/page/alphatab
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=1.9.0
SHA256=e9e9b795f9803fda6cf00c0e6c8cb412c6e1033fb7979fc1bc40c1e1ecccaf35
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
