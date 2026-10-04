#!/usr/bin/env bash
# The screenshots of every screen of Bandroom for Mac in every variant (the screen catalogue, Tests/), and what
# changed in them.
#
#   scripts/screenshots.sh record            take them, with the catalogue's checks: build/catalogue/screenshots/
#   scripts/screenshots.sh compare [base]    take them at <base> (default: the merge base with origin/main), then
#                                            here with the checks, and report what differs
#
# The catalogue runs in a Debug build of the app hosting its unit tests, off screen: no window is shown, no menu-bar
# item is made, and the app runs on canned engine answers with data of its own, so it can be run on a Mac in use. It
# runs twice: in English and in bokmål (xcodebuild -testLanguage nb).
#
# The screenshots are not kept in git: a few hundred PNGs that change with every design change would grow the
# repository for good. A change is compared instead with the commit it started from, in the same run on the same
# machine, so the fonts and the drawing code are the same on both sides.
#
# compare writes build/reports/screenshots/: index.html (before, the difference and after, for each screen that
# changed), summary.md (the same as a list) and the images. It exits 0 when no screen changed, 1 when one changed,
# appeared or went away, 2 when the catalogue's own checks failed (names, target sizes, cut-off text, reading order),
# and 3 when anything on the base's side failed (its worktree, build or screenshots) or the comparison could not run
# (nothing was compared; summary.md says so). A label may only let 1 through.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
app="$(cd "$here/.." && pwd)"
repo="$(cd "$app/../../.." && pwd)"
report="$app/build/reports/screenshots"
shots="$app/build/catalogue/screenshots"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

log() { printf 'screenshots: %s\n' "$*" >&2; }

# Builds the Bandroom checkout $1 for testing; then runs its catalogue into $2, in English and in bokmål.
# CATALOGUE_CHECKS=0 takes only the screenshots.
build() {
  (cd "$1" && xcodegen generate --quiet \
    && xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribeBandroom \
         -destination 'platform=macOS' build-for-testing -quiet)
}
catalogue() {
  local dir="$1" out="$2" status=0 lang
  rm -rf "$out"; mkdir -p "$out"
  for lang in en nb; do
    (cd "$dir" && TEST_RUNNER_CATALOGUE_OUT="$out" TEST_RUNNER_CATALOGUE_CHECKS="${CATALOGUE_CHECKS:-1}" \
      xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribeBandroom \
        -destination 'platform=macOS' -testLanguage "$lang" -only-testing:BrasscribeBandroomTests/BandroomScreensTests \
        test-without-building -quiet) || status=1
  done
  return "$status"
}

case "${1:-}" in
  record)
    build "$app"
    catalogue "$app" "$shots"
    log "$(find "$shots" -name '*.png' | wc -l | tr -d ' ') screenshots in apps/bandroom/macos/build/catalogue/screenshots"
    ;;
  compare)
    rm -rf "$report"; mkdir -p "$report"
    # Anything that goes wrong on the base's side, whatever its own exit code, is 3: never "screens changed",
    # which the label could let through.
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
    if [ -d "$tree/apps/bandroom/macos/Tests" ]; then
      log "taking them at ${base:0:12}"
      # What is not in git, as this checkout has it: the data folder (band sounds) and the download cache of the build.
      [ -e "$repo/data" ] && ln -s "$repo/data" "$tree/data"
      if [ -d "$app/build/cache" ]; then mkdir -p "$tree/apps/bandroom/macos/build" && ln -s "$app/build/cache" "$tree/apps/bandroom/macos/build/cache"; fi
      build "$tree/apps/bandroom/macos" || no_base
      # Only the screenshots: the base's own findings are not this change's.
      CATALOGUE_CHECKS=0 catalogue "$tree/apps/bandroom/macos" "$report/before" || no_base
    else
      log "${base:0:12} has no screen catalogue: every screen is new"
    fi
    log "taking them here, with the checks, and comparing"
    build "$app" || exit 2
    # A screen that fails its checks is reported by the tests; the comparison is made all the same.
    checks=0
    catalogue "$app" "$shots" || checks=2
    rm -f "$report/result.json"
    xcrun swift "$repo/scripts/screenshot-compare.swift" "$report/before" "$shots" "$report" || true
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
    sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
