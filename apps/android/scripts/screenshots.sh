#!/usr/bin/env bash
# The screenshots of every screen of both apps (the screen catalogues, taken on the JVM by Roborazzi),
# and what changed in them.
#
#   apps/android/scripts/screenshots.sh record            take them: app/build/outputs/roborazzi/<app>/
#   apps/android/scripts/screenshots.sh compare [base]    take them at <base> (default: the merge base with
#                                                         origin/main), then here, and report what differs
#
# SCREENSHOT_APPS="brasscribe" (or "fretscribe") limits both to one app; the default is both.
#
# The screenshots are not kept in git: a few hundred PNGs that change with every design change would
# grow the repository for good. A change is compared instead with the commit it started from, in the
# same run on the same machine, so the fonts and the drawing code are the same on both sides.
#
# compare writes app/build/reports/screenshots/: index.html (before, the difference and after, for
# each screen that changed), summary.md (the same as a list) and the images. It exits 0 when no screen
# changed, 1 when one changed, appeared or went away, 2 when the catalogues' own checks failed
# (accessibility, text cut off at 200 %, the keyboard's order), and 3 when the screenshots could not be
# taken at the base (nothing was compared; summary.md says so).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
android="$(cd "$here/.." && pwd)"
repo="$(cd "$android/../.." && pwd)"
report="$android/app/build/reports/screenshots"
catalogues=()
for app in ${SCREENSHOT_APPS:-brasscribe fretscribe}; do
  case "$app" in
    brasscribe) catalogues+=(":app:testBrasscribeDebugUnitTest" --tests "*BrasscribeScreensTest") ;;
    fretscribe) catalogues+=(":app:testFretscribeDebugUnitTest" --tests "*FretscribeScreensTest") ;;
    *) echo "screenshots: no app $app (brasscribe, fretscribe)" >&2; exit 2 ;;
  esac
done

log() { printf 'screenshots: %s\n' "$*" >&2; }

# Runs the screen catalogues of the checkout whose apps/android is $1, with Roborazzi in mode $2.
catalogues() {
  (cd "$1" && rm -rf app/build/test-results/roborazzi && ./gradlew "${catalogues[@]}" "-Proborazzi.test.$2=true" --console=plain -q)
}

case "${1:-}" in
  record)
    rm -rf "$android/app/build/outputs/roborazzi"
    catalogues "$android" record
    log "$(find "$android/app/build/outputs/roborazzi" -name '*.png' | wc -l | tr -d ' ') screenshots in apps/android/app/build/outputs/roborazzi"
    ;;
  compare)
    base="${2:-$(git -C "$repo" merge-base HEAD origin/main)}"
    rm -rf "$report"; mkdir -p "$report/before"
    tree="$(mktemp -d)/base"
    trap 'git -C "$repo" worktree remove --force "$tree" >/dev/null 2>&1 || true' EXIT
    git -C "$repo" worktree add --detach "$tree" "$base" >/dev/null
    if [ -f "$tree/apps/android/scripts/screenshots.sh" ]; then
      log "taking them at ${base:0:12}"
      # What is not in git, as this checkout has it.
      for dir in data models; do [ -e "$repo/$dir" ] && ln -s "$repo/$dir" "$tree/$dir"; done
      if git -C "$repo" diff --quiet "$base" HEAD -- core && [ -d "$repo/core/target/release" ]; then
        mkdir -p "$tree/core/target" && ln -s "$repo/core/target/release" "$tree/core/target/release"
      else
        log "the core differs at ${base:0:12}: building its host library there"
        (cd "$tree/core" && cargo build --release -p brasscribe-ffi)
      fi
      rm -rf "$tree/apps/android/app/build/outputs/roborazzi"
      if ! catalogues "$tree/apps/android" record; then
        log "the screenshots could not be taken at ${base:0:12}: nothing was compared"
        printf '# Screenshots\n\nThe screenshots could not be taken at the base, %s, so nothing was compared.\n' "${base:0:12}" >"$report/summary.md"
        exit 3
      fi
      cp -R "$tree/apps/android/app/build/outputs/roborazzi/." "$report/before/"
    else
      log "${base:0:12} has no screen catalogue: every screen is new"
    fi
    log "taking them here, and comparing"
    out="$android/app/build/outputs/roborazzi"
    rm -rf "$out"; mkdir -p "$out"
    cp -R "$report/before/." "$out/"
    # A screen that fails its checks is reported by the tests; the comparison is made all the same.
    checks=0
    catalogues "$android" compare || checks=2
    changed=0
    python3 "$here/screenshot_report.py" "$report/before" "$android/app/build/test-results/roborazzi" "$report" || changed=1
    [ "$checks" -ne 0 ] && { log "the screen catalogues' checks failed (app/build/reports/tests)"; exit 2; }
    exit "$changed"
    ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
