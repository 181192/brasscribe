#!/usr/bin/env bash
# Assemble the GitHub Pages site into site/_site from site/ plus the design system's generated assets.
# Usage: site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/site/_site"
rm -rf "$OUT"
mkdir -p "$OUT/assets/logo" "$OUT/assets/shots"

# Every page is a directory with an index.html, so URLs have no .html.
cp "$ROOT"/site/{index.html,site.css,lang.js} "$OUT/"
cp -R "$ROOT/site/guide" "$ROOT/site/nb" "$OUT/"
cp -R "$ROOT/design/dist/web/brasscribe.css" "$ROOT/design/dist/web/fonts.css" "$ROOT/design/dist/web/fonts" "$OUT/assets/"
cp "$ROOT"/design/dist/icons/web/* "$OUT/"
cp "$ROOT"/design/brand/logo/{lockup-play,lockup-play-on-dark,mark-brass,mark}.svg "$OUT/assets/logo/"

for s in home first-run what-is-this transcribing review choose-output score part export error; do
  for v in phone-light phone-dark desktop-light desktop-dark nb-phone-light nb-desktop-light; do
    f="$ROOT/design/mockups/png/$s-$v.png"
    [ -f "$f" ] && cp "$f" "$OUT/assets/shots/"
  done
done
touch "$OUT/.nojekyll"
echo "site built in $OUT"
