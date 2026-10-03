#!/usr/bin/env bash
# Screenshots of every screen of both apps, taken on the JVM (Roborazzi), and what changed in them.
#
#   apps/android/scripts/screenshots.sh record             take them: app/build/outputs/roborazzi/<app>/...
#   apps/android/scripts/screenshots.sh compare [base]     take them at <base> (default: the merge base with
#                                                          origin/main), then here, and report what differs
#
# The screenshots are not kept in git: a few hundred PNGs that change with every design change would
# grow the repository for good. Instead a change is compared with the commit it started from, on the
# same machine in the same run, so the fonts and the drawing code are the same on both sides.
#
# compare writes app/build/reports/screenshots/: index.html (before, after and the difference of each
# changed screen), summary.md (the same as a list), and the images. It exits 1 when a screen changed,
# appeared or went away, and 0 when nothing did. A change that is meant is looked at in that report.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
android="$(cd "$here/.." && pwd)"
repo="$(cd "$android/../.." && pwd)"
out="$android/app/build/outputs/roborazzi"
report="$android/app/build/reports/screenshots"
tasks=(":app:testBrasscribeDebugUnitTest" ":app:testFretscribeDebugUnitTest")

log() { printf 'screenshots: %s\n' "$*" >&2; }

# Takes the screenshots of the checkout at $1 (its apps/android), into its own build directory.
record() {
  rm -rf "$1/app/build/outputs/roborazzi"
  (cd "$1" && ./gradlew "${tasks[@]}" -Proborazzi.test.record=true --console=plain -q)
}

case "${1:-}" in
  record)
    record "$android"
    log "$(find "$out" -name '*.png' | wc -l | tr -d ' ') screenshots in ${out#"$repo"/}"
    ;;
  compare)
    base="${2:-$(git -C "$repo" merge-base HEAD origin/main)}"
    tree="$(mktemp -d)/base"
    trap 'git -C "$repo" worktree remove --force "$tree" >/dev/null 2>&1 || true' EXIT
    log "taking them at ${base:0:12}"
    git -C "$repo" worktree add --detach "$tree" "$base" >/dev/null
    before="$report/before"
    rm -rf "$report"; mkdir -p "$before"
    if [ -f "$tree/apps/android/scripts/screenshots.sh" ]; then
      # What is not in git, as this checkout has it: the design's generated files are, the core's host build is not.
      for dir in data models; do [ -e "$repo/$dir" ] && ln -s "$repo/$dir" "$tree/$dir"; done
      if git -C "$repo" diff --quiet "$base" HEAD -- core && [ -d "$repo/core/target/release" ]; then
        mkdir -p "$tree/core/target" && ln -s "$repo/core/target/release" "$tree/core/target/release"
      else
        log "the core differs from $base: building its host library there"
        (cd "$tree/core" && cargo build --release -p brasscribe-ffi)
      fi
      record "$tree/apps/android"
      cp -R "$tree/apps/android/app/build/outputs/roborazzi/." "$before/"
    else
      log "${base:0:12} has no screenshots to take: every screen counts as new"
    fi
    log "taking them here"
    record "$android"
    python3 "$here/screenshot_report.py" "$before" "$out" "$report"
    ;;
  *)
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
