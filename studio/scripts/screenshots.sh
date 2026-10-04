#!/usr/bin/env bash
# The screenshots of every view of Studio in every variant (the screen catalogue, catalogue/), and what
# changed in them.
#
#   studio/scripts/screenshots.sh record            take them, with the catalogue's checks: build/catalogue/screenshots/
#   studio/scripts/screenshots.sh compare [base]    take them at <base> (default: the merge base with origin/main),
#                                                   then here with the checks, and report what differs
#
# The screenshots are not kept in git: a few hundred PNGs that change with every design change would grow
# the repository for good. A change is compared instead with the commit it started from, in the same run on
# the same machine, so the fonts and the browser are the same on both sides.
#
# compare writes build/reports/screenshots/: index.html (before, the difference and after, for each view that
# changed), summary.md (the same as a list) and the images. It exits 0 when no view changed, 1 when one
# changed, appeared or went away, 2 when the catalogue's own checks failed (accessibility, cut-off text, the
# page fitting 320 px and 200 %, text spacing, the keyboard, and the checks' own tests), and 3 when anything
# on the base's side failed (its worktree, npm packages, build or screenshots) or the comparison could not
# run (nothing was compared; summary.md says so). A label may only let 1 through.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
studio="$(cd "$here/.." && pwd)"
repo="$(cd "$studio/.." && pwd)"
report="$studio/build/reports/screenshots"
shots="$studio/build/catalogue/screenshots"

log() { printf 'screenshots: %s\n' "$*" >&2; }
free_port() { node -e 'const s = require("node:net").createServer().listen(0, "127.0.0.1", () => { console.log(s.address().port); s.close(); })'; }

# Builds the bundle of the Studio checkout $1 and runs its catalogue there into $2; the rest are Playwright's.
catalogue() {
  local dir="$1" out="$2"; shift 2
  rm -rf "$out"
  (cd "$dir" && npm run build --silent >/dev/null \
    && CATALOGUE_SHOTS="$out" STUDIO_STATIC_PORT="$(free_port)" npx playwright test -c playwright.catalogue.config.ts "$@")
}

case "${1:-}" in
  record)
    catalogue "$studio" "$shots"
    log "$(find "$shots" -name '*.png' | wc -l | tr -d ' ') screenshots in studio/build/catalogue/screenshots"
    ;;
  compare)
    rm -rf "$report"; mkdir -p "$report"
    # Anything that goes wrong on the base's side, whatever its own exit code, is 3: never "views changed",
    # which the label could let through.
    # The base as given (or the merge base), until it is known as a commit.
    ref="${2:-the merge base with origin/main}"
    no_base() {
      log "the screenshots could not be taken at $ref: nothing was compared"
      printf '# Screenshots\n\nThe screenshots could not be taken at the base, %s, so nothing was compared.\n' "$ref" >"$report/summary.md"
      exit 3
    }
    base="${2:-}"
    [ -n "$base" ] || base="$(git -C "$repo" merge-base HEAD origin/main)" || no_base
    base="$(git -C "$repo" rev-parse --verify --quiet "$base^{commit}")" || no_base
    ref="${base:0:12}"
    scratch="$(mktemp -d)" || no_base
    tree="$scratch/base"
    trap 'git -C "$repo" worktree remove --force "$tree" >/dev/null 2>&1 || true; rm -rf "$scratch"' EXIT
    git -C "$repo" worktree add --detach "$tree" "$base" >/dev/null || no_base
    if [ -f "$tree/studio/catalogue/catalogue.spec.ts" ]; then
      log "taking them at ${base:0:12}"
      if cmp -s "$studio/package-lock.json" "$tree/studio/package-lock.json" && [ -d "$studio/node_modules" ]; then
        ln -s "$studio/node_modules" "$tree/studio/node_modules" || no_base
      else
        log "the base has other npm packages: installing them there"
        (cd "$tree/studio" && npm ci --no-audit --no-fund >/dev/null && npx playwright install chromium >/dev/null) || no_base
      fi
      # Only the screenshots: the base's own findings are not this change's.
      CATALOGUE_CHECKS=0 catalogue "$tree/studio" "$report/before" catalogue.spec || no_base
    else
      log "${base:0:12} has no screen catalogue: every view is new"
    fi
    log "taking them here, with the checks, and comparing"
    # A view that fails its checks is reported by the tests; the comparison is made all the same.
    checks=0
    catalogue "$studio" "$shots" || checks=2
    # The comparison's answer is the result file it writes last; without it (it could not run), nothing was compared.
    rm -f "$report/result.json"
    node "$studio/catalogue/compare.mjs" "$report/before" "$shots" "$report" || true
    if [ ! -f "$report/result.json" ]; then
      log "the screenshots could not be compared"
      printf '# Screenshots\n\nThe comparison could not run, so nothing was compared.\n' >"$report/summary.md"
      exit 3
    fi
    [ "$checks" -ne 0 ] && { log "the catalogue's checks failed (see the test output above)"; exit 2; }
    grep -q '"any": *true' "$report/result.json" && exit 1
    exit 0
    ;;
  *)
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
