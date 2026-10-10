#!/usr/bin/env bash
# Is the change from BASE to HEAD only a release's version? Exit 0 when every changed file is CHANGELOG.md or one
# of the files scripts/release.sh writes the version into, and every changed line in those is a version line; 1
# otherwise (and when nothing changed). ci.yml starts no platform job for such a pull request.
#
#   .github/scripts/version-only.sh BASE HEAD
#
# The list is release.sh's. A file added there and not here only means a release pull request runs every job.
set -euo pipefail
base="$1" head="$2"

files="$(git diff --name-only "$base" "$head")"
[ -n "$files" ] || exit 1
while IFS= read -r file; do
  case "$file" in
    CHANGELOG.md) continue ;;
    apps/android/app/build.gradle.kts) line='^[+-] *(versionCode = [0-9]+|versionName = "[0-9A-Za-z.+-]+")$' ;;
    apps/apple/project.yml | apps/bandroom/macos/project.yml) line='^[+-] *(MARKETING_VERSION|CURRENT_PROJECT_VERSION): "[0-9A-Za-z.+-]+"$' ;;
    apps/windows/Directory.Build.props | apps/bandroom/windows/Directory.Build.props) line='^[+-] *<Version>[0-9A-Za-z.+-]+</Version>$' ;;
    *) exit 1 ;;
  esac
  # The changed lines, without the two file headers.
  if git diff -U0 "$base" "$head" -- "$file" | grep -E '^[+-]' | grep -vE '^(\+\+\+|---) ' | grep -qvE "$line"; then exit 1; fi
done <<< "$files"
exit 0
