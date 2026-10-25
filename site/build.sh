#!/usr/bin/env bash
# Assemble the GitHub Pages site into site/_site from site/shared and site/brasscribe plus the design system's generated assets.
# Usage: site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/site/_site"

# The site and the READMEs link to the latest release and never name a version, so nothing goes stale.
pinned=$(cd "$ROOT" && git grep -n -I -E 'releases/tag/v[0-9]|releases/download/v[0-9]|Brasscribe [0-9]+\.[0-9]+\.[0-9]|[Vv]ersjon [0-9]+\.[0-9]+|[Vv]ersion [0-9]+\.[0-9]+\.[0-9]|[Rr]elease v[0-9]' \
  -- 'site/*.html' 'README.md' '*/README.md' ':!site/brasscribe/research' ':!site/brasscribe/nb/research' || true)
if [ -n "$pinned" ]; then
  echo "error: link to releases/latest instead of naming a version:" >&2; echo "$pinned" >&2; exit 1
fi
rm -rf "$OUT"
mkdir -p "$OUT/assets/logo"

# Every page is a directory with an index.html, so URLs have no .html.
# site/shared has what every product page uses; site/brasscribe is the product, served at the site root.
cp "$ROOT"/site/shared/{site.css,lang.js} "$OUT/"
cp "$ROOT/site/brasscribe/index.html" "$OUT/"
cp -R "$ROOT/site/brasscribe/guide" "$ROOT/site/brasscribe/research" "$ROOT/site/brasscribe/nb" "$OUT/"
cp -R "$ROOT/design/brands/brasscribe/dist/web/brasscribe.css" "$ROOT/design/brands/brasscribe/dist/web/fonts.css" "$ROOT/design/brands/brasscribe/dist/web/fonts" "$OUT/assets/"
cp "$ROOT"/design/brands/brasscribe/dist/icons/web/* "$OUT/"
cp "$ROOT"/design/brands/brasscribe/brand/logo/{lockup-play,lockup-play-on-dark,mark-brass,mark}.svg "$OUT/assets/logo/"

# Screenshots of the real apps, made from site/brasscribe/shots.txt by site/brasscribe/make_shots.py.
cp -R "$ROOT/site/brasscribe/shots" "$OUT/assets/shots"
touch "$OUT/.nojekyll"
echo "site built in $OUT"
