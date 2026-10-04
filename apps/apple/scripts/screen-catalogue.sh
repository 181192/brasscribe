#!/usr/bin/env bash
# The screenshots of every screen of Play for Mac in every variant (the screen catalogue,
# AppTests/PlayScreensTests.swift), and what changed in them. Run through scripts/screenshots.sh:
#
#   scripts/screenshots.sh record            take them, with the catalogue's checks: build/catalogue/screenshots/
#   scripts/screenshots.sh compare [base]    take them at <base> (default: the merge base with origin/main), then
#                                            here with the checks, and report what differs
#
# The catalogue runs in the macOS app's unit-test bundle, hosted by the app as UnitTestHost: no window is shown,
# so it can be run on a Mac in use. It runs twice: in English and in bokmål (xcodebuild -testLanguage nb).
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
repo="$(cd "$app/../.." && pwd)"
report="$app/build/reports/screenshots"
shots="$app/build/catalogue/screenshots"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

log() { printf 'screenshots: %s\n' "$*" >&2; }

# Builds the macOS app's tests in the Play checkout $1; then runs its catalogue into $2, in English and in bokmål.
# CATALOGUE_CHECKS=0 takes only the screenshots.
build() {
  local log; log="$(mktemp)"
  make -C "$1" build-for-testing-mac >"$log" 2>&1 || { grep -E "error:" "$log" | sort -u | head -40 >&2; tail -20 "$log" >&2; rm -f "$log"; return 1; }
  rm -f "$log"
}
catalogue() {
  local dir="$1" out="$2" status=0 lang
  rm -rf "$out"; mkdir -p "$out"
  # Only what failed, and the totals: the rest of what the tests print is the app's own logging.
  for lang in en nb; do
    (cd "$dir" && TEST_RUNNER_CATALOGUE_OUT="$out" TEST_RUNNER_CATALOGUE_CHECKS="${CATALOGUE_CHECKS:-1}" \
      xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribePlay-macOS \
        -destination 'platform=macOS' -testLanguage "$lang" -only-testing:BrasscribePlayTests_macOS/PlayScreensTests \
        test-without-building 2>&1 | { grep -E "^(✘|↳|✔ Test run|Failing tests|Restarting)|^\t[A-Za-z].*\(\)$|: error:" || true; }) || status=1
  done
  return "$status"
}

case "${1:-}" in
  record)
    build "$app"
    catalogue "$app" "$shots"
    log "$(find "$shots" -name '*.png' | wc -l | tr -d ' ') screenshots in apps/apple/build/catalogue/screenshots"
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
    if [ -f "$tree/apps/apple/AppTests/PlayScreensTests.swift" ]; then
      log "taking them at ${base:0:12}"
      # What is not in git, as this checkout has it: the data folder, Verovio (when its build script is the same) and the
      # core's xcframework (when the core is the same; otherwise it is built there).
      [ -e "$repo/data" ] && ln -s "$repo/data" "$tree/data"
      if git -C "$repo" diff --quiet "$base" HEAD -- apps/apple/scripts/build-verovio.sh && [ -d "$app/Frameworks" ]; then
        ln -s "$(cd "$app/Frameworks" && pwd -P)" "$tree/apps/apple/Frameworks"
      else
        log "Verovio's build differs at ${base:0:12}: building it there"
        make -C "$tree/apps/apple" verovio >/dev/null || no_base
      fi
      xcf="core/swift/BrasscribeCore/BrasscribeFFI.xcframework"
      if git -C "$repo" diff --quiet "$base" HEAD -- core && [ -d "$repo/$xcf" ]; then
        rm -rf "${tree:?}/$xcf" && cp -R "$repo/$xcf" "$tree/$xcf"
      else
        log "the core differs at ${base:0:12}: building its xcframework there"
        (cd "$tree/apps/apple" && scripts/build-core.sh >/dev/null) || no_base
      fi
      build "$tree/apps/apple" || no_base
      # Only the screenshots: the base's own findings are not this change's.
      CATALOGUE_CHECKS=0 catalogue "$tree/apps/apple" "$report/before" || no_base
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
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
