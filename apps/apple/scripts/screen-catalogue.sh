#!/usr/bin/env bash
# Play for Mac's screen catalogue (products/brasscribe/AppTests/PlayScreensTests.swift): every screen in every variant with its checks
# (names, target sizes, cut-off text, reading order), and a screenshot of each. Run through scripts/screenshots.sh:
#
#   scripts/screenshots.sh record             build the macOS app's tests and run it: the screenshots and each screen's
#                                             tree are in build/catalogue/screenshots/
#   scripts/screenshots.sh record fretscribe  the same for Fretscribe for Mac (AppTests/FretscribeScreensTests.swift),
#                                             into build/catalogue/fretscribe/
#
# The catalogue runs in the macOS app's unit-test bundle, hosted by the app as UnitTestHost: no window is shown,
# so it can be run on a Mac in use. It runs twice: in English and in bokmål (xcodebuild -testLanguage nb).
#
# It fails when a screen fails a check, or is not taken because it did not become the screen asked for (its last
# picture is then in not-taken/; takes-<language>.log says what each screen waited for). The screenshots are to look
# at; they are not kept in git, and nothing here compares them. After a merge, CI compares main's with those of the
# main before it (.github/workflows/screens.yml), and that blocks nothing.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
app="$(cd "$here/.." && pwd)"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

case "${1:-}" in
  record)
    case "${2:-brasscribe}" in
      brasscribe) shots="$app/build/catalogue/screenshots"; build=build-for-testing-mac
        project=products/brasscribe/BrasscribePlay.xcodeproj; derived=build/DerivedData; scheme=BrasscribePlay-macOS
        only=BrasscribePlayTests_macOS/PlayScreensTests ;;
      fretscribe) shots="$app/build/catalogue/fretscribe"; build=build-for-testing-fretscribe-mac
        project=products/fretscribe/Fretscribe.xcodeproj; derived=build/DerivedData-fs; scheme=Fretscribe-macOS
        only=FretscribeTests_macOS/FretscribeScreensTests ;;
      *) echo "unknown product: $2" >&2; exit 2 ;;
    esac
    log="$(mktemp)"
    make -C "$app" "$build" >"$log" 2>&1 || { grep -E "error:" "$log" | sort -u | head -40 >&2; tail -20 "$log" >&2; rm -f "$log"; exit 1; }
    rm -f "$log"
    rm -rf "$shots"; mkdir -p "$shots"
    status=0
    # Only what failed, and the totals: the rest of what the tests print is the app's own logging.
    for lang in en nb; do
      (cd "$app" && TEST_RUNNER_CATALOGUE_OUT="$shots" TEST_RUNNER_CATALOGUE_LANGUAGE="$lang" \
        xcodebuild -project "$project" -derivedDataPath "$derived" -scheme "$scheme" \
          -destination 'platform=macOS' -testLanguage "$lang" -only-testing:"$only" \
          test-without-building 2>&1 | { grep -E "^(✘|↳|✔ Test run|Failing tests|Restarting)|^\t[A-Za-z].*\(\)$|: error:" || true; }) || status=1
    done
    printf 'screenshots: %s screenshots in %s\n' "$(find "$shots" -name '*.png' | wc -l | tr -d ' ')" "${shots#"$app/"}" >&2
    exit "$status"
    ;;
  *)
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
