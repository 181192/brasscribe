#!/usr/bin/env bash
# Bandroom for Mac's screen catalogue (Tests/): every screen in every variant with its checks (names, target sizes,
# cut-off text, reading order), and a screenshot of each.
#
#   scripts/screenshots.sh record    build the app for testing and run it: the screenshots and each screen's tree
#                                    are in build/catalogue/screenshots/
#
# The catalogue runs in a Debug build of the app hosting its unit tests, off screen: no window is shown, no menu-bar
# item is made, and the app runs on canned engine answers with data of its own, so it can be run on a Mac in use. It
# runs twice: in English and in bokmål (xcodebuild -testLanguage nb).
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
    (cd "$app" && xcodegen generate --quiet \
      && xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribeBandroom \
           -destination 'platform=macOS' build-for-testing -quiet)
    rm -rf "$shots"; mkdir -p "$shots"
    status=0
    # Only what failed, and the totals: the rest of what the tests print is the app's own logging.
    for lang in en nb; do
      (cd "$app" && TEST_RUNNER_CATALOGUE_OUT="$shots" \
        xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath build/DerivedData -scheme BrasscribeBandroom \
          -destination 'platform=macOS' -testLanguage "$lang" -only-testing:BrasscribeBandroomTests \
          test-without-building 2>&1 | { grep -E "^(✘|↳|✔ Test run|Failing tests|Restarting)|^\t[A-Za-z].*\(\)$|: error:" || true; }) || status=1
    done
    printf 'screenshots: %s screenshots in apps/bandroom/macos/build/catalogue/screenshots\n' "$(find "$shots" -name '*.png' | wc -l | tr -d ' ')" >&2
    exit "$status"
    ;;
  *)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
