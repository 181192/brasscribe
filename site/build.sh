#!/usr/bin/env bash
# Assemble the GitHub Pages site into site/_site from site/ plus the design system's generated assets.
# Usage: site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/site/_site"
rm -rf "$OUT"
mkdir -p "$OUT/assets/logo"

# Every page is a directory with an index.html, so URLs have no .html.
cp "$ROOT"/site/{index.html,site.css,lang.js} "$OUT/"
cp -R "$ROOT/site/guide" "$ROOT/site/nb" "$OUT/"
cp -R "$ROOT/design/dist/web/brasscribe.css" "$ROOT/design/dist/web/fonts.css" "$ROOT/design/dist/web/fonts" "$OUT/assets/"
cp "$ROOT"/design/dist/icons/web/* "$OUT/"
cp "$ROOT"/design/brand/logo/{lockup-play,lockup-play-on-dark,mark-brass,mark}.svg "$OUT/assets/logo/"

# Screenshots of the real apps, made from site/shots.txt by site/make_shots.py.
cp -R "$ROOT/site/shots" "$OUT/assets/shots"
touch "$OUT/.nojekyll"
echo "site built in $OUT"
