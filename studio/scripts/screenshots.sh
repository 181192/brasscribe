#!/usr/bin/env bash
# Studio's screen catalogue (catalogue/): every view in every variant with its checks (accessibility, cut-off text,
# the page fitting 320 px and 200 %, text spacing, the keyboard, and the checks' own tests), and a screenshot of each.
#
#   studio/scripts/screenshots.sh record    build the bundle and run it: the screenshots are in
#                                           build/catalogue/screenshots/
#
# It fails when a view fails a check. No check reads the screenshots: they are to look at (`npm run test:catalogue`
# runs the same checks without taking them). They are not kept in git, and nothing here compares them. After a
# merge, CI compares main's with those of the main before it (.github/workflows/screens.yml, with
# catalogue/compare.mjs), and that blocks nothing.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
studio="$(cd "$here/.." && pwd)"
shots="$studio/build/catalogue/screenshots"

free_port() { node -e 'const s = require("node:net").createServer().listen(0, "127.0.0.1", () => { console.log(s.address().port); s.close(); })'; }

case "${1:-}" in
  record)
    rm -rf "$shots"
    (cd "$studio" && npm run build --silent >/dev/null \
      && CATALOGUE_SHOTS="$shots" STUDIO_STATIC_PORT="$(free_port)" npx playwright test -c playwright.catalogue.config.ts)
    printf 'screenshots: %s screenshots in studio/build/catalogue/screenshots\n' "$(find "$shots" -name '*.png' | wc -l | tr -d ' ')" >&2
    ;;
  *)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
