#!/usr/bin/env bash
# The screen catalogues of both apps on the JVM: every screen in every variant with its checks (accessibility,
# text cut off at 200 %, the keyboard's order), and a screenshot of each, taken by Roborazzi.
#
#   apps/android/scripts/screenshots.sh record    run them: the screenshots are in app/build/outputs/roborazzi/<app>/
#
# SCREENSHOT_APPS="brasscribe" (or "fretscribe") limits it to one app; the default is both.
#
# It fails when a screen fails a check or could not be taken. The screenshots are to look at; they are not kept
# in git, and nothing here compares them. After a merge, CI compares main's with those of the main before it
# (.github/workflows/screens.yml), and that blocks nothing.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
android="$(cd "$here/.." && pwd)"
catalogues=()
for app in ${SCREENSHOT_APPS:-brasscribe fretscribe}; do
  case "$app" in
    brasscribe) catalogues+=(":app:testBrasscribeDebugUnitTest" --tests "*BrasscribeScreensTest") ;;
    fretscribe) catalogues+=(":app:testFretscribeDebugUnitTest" --tests "*FretscribeScreensTest") ;;
    *) echo "screenshots: no app $app (brasscribe, fretscribe)" >&2; exit 2 ;;
  esac
done

case "${1:-}" in
  record)
    rm -rf "$android/app/build/outputs/roborazzi" "$android/app/build/test-results/roborazzi"
    (cd "$android" && ./gradlew "${catalogues[@]}" -Proborazzi.test.record=true --console=plain -q)
    printf 'screenshots: %s screenshots in apps/android/app/build/outputs/roborazzi\n' \
      "$(find "$android/app/build/outputs/roborazzi" -name '*.png' | wc -l | tr -d ' ')" >&2
    ;;
  *)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
