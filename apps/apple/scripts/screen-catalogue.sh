#!/usr/bin/env bash
# Play for Mac's screen catalogue (AppTests/PlayScreensTests.swift): every screen in every variant with its checks
# (names, target sizes, cut-off text, reading order), and a screenshot of each. Run through scripts/screenshots.sh:
#
#   scripts/screenshots.sh record    build the macOS app's tests and run it: the screenshots and each screen's
#                                    tree are in build/catalogue/screenshots/
#
# The catalogue runs in the macOS app's unit-test bundle, hosted by the app as UnitTestHost: no window is shown,
# so it can be run on a Mac in use. It runs twice: in English and in bokmål (xcodebuild -testLanguage nb).
#
# It fails when a screen fails a check. The screenshots are to look at; they are not kept in git, and nothing here
# compares them. After a merge, CI compares main's with those of the main before it
# (.github/workflows/screens.yml), and that blocks nothing.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
app="$(cd "$here/.." && pwd)"
shots="$app/build/catalogue/screenshots"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

case "${1:-}" in
  record)
    log="$(mktemp)"
    make -C "$app" build-for-testing-mac >"$log" 2>&1 || { grep -E "error:" "$log" | sort -u | head -40 >&2; tail -20 "$log" >&2; rm -f "$log"; exit 1; }
    rm -f "$log"
    rm -rf "$shots"; mkdir -p "$shots"
    status=0
    # Only what failed, and the totals: the rest of what the tests print is the app's own logging.
    for lang in en nb; do
      (cd "$app" && TEST_RUNNER_CATALOGUE_OUT="$shots" \
        xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribePlay-macOS \
          -destination 'platform=macOS' -testLanguage "$lang" -only-testing:BrasscribePlayTests_macOS/PlayScreensTests \
          test-without-building 2>&1 | { grep -E "^(✘|↳|✔ Test run|Failing tests|Restarting)|^\t[A-Za-z].*\(\)$|: error:" || true; }) || status=1
    done
    printf 'screenshots: %s screenshots in apps/apple/build/catalogue/screenshots\n' "$(find "$shots" -name '*.png' | wc -l | tr -d ' ')" >&2
    exit "$status"
    ;;
  *)
    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
