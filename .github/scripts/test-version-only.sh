#!/usr/bin/env bash
# Tests of version-only.sh: the last five release commits of this repository are "only the version"; changes made
# here to copies of the version files, each of which changes something else, are not. Needs the repository's
# history (a full checkout). Run from anywhere in the checkout.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
script="$root/.github/scripts/version-only.sh"
failed=0

expect() { # expect 0|1 WHAT BASE HEAD   (in the current directory's repository)
  local got=0
  "$script" "$3" "$4" || got=$?
  if [ "$got" = "$1" ]; then echo "ok: $2"; else echo "FAILED: $2 (exit $got, expected $1)"; failed=1; fi
}

# ---- the real release commits
cd "$root"
releases="$(git log --format=%H -E --grep='^chore\(release\): [0-9]+\.[0-9]+\.[0-9]+' -5 HEAD)"
[ "$(wc -l <<< "$releases" | tr -d ' ')" = 5 ] || { echo "FAILED: fewer than five release commits in this checkout's history (a shallow checkout?)"; exit 1; }
while IFS= read -r commit; do
  expect 0 "$(git log -1 --format=%s "$commit")" "$commit^" "$commit"
done <<< "$releases"

# ---- made-up changes, in a repository of their own that holds the version files as they are here
files="apps/android/app/build.gradle.kts apps/apple/project.yml apps/bandroom/macos/project.yml apps/windows/Directory.Build.props apps/bandroom/windows/Directory.Build.props"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git init -q "$work"
for f in $files CHANGELOG.md; do mkdir -p "$work/$(dirname "$f")"; git -C "$root" show "HEAD:$f" > "$work/$f"; done
cd "$work"
git config user.name test; git config user.email test@example.invalid
git add -A; git commit -q -m base
base="$(git rev-parse HEAD)"

bump() { # what release.sh writes, in every file
  sed -i.bak -E 's/^( *versionCode = )[0-9]+/\19999/; s/^( *versionName = )"[^"]*"/\1"99.0.0"/' apps/android/app/build.gradle.kts
  sed -i.bak -E 's/^( *MARKETING_VERSION: )"[^"]*"/\1"99.0.0"/; s/^( *CURRENT_PROJECT_VERSION: )"[^"]*"/\1"9999"/' apps/apple/project.yml apps/bandroom/macos/project.yml
  sed -i.bak -E 's#<Version>[^<]*</Version>#<Version>99.0.0</Version>#' apps/windows/Directory.Build.props apps/bandroom/windows/Directory.Build.props
  echo "## 99.0.0" >> CHANGELOG.md
  find . -name '*.bak' -delete
}
# Commits what the working tree holds, checks it, and goes back to the base.
check() { # check 0|1 WHAT
  git add -A; git commit -q -m "$2"
  expect "$1" "$2" "$base" HEAD
  git reset -q --hard "$base"
}

bump; check 0 "a made-up release: the version in every file, and the changelog"
check_nothing() { expect 1 "nothing changed" "$base" "$base"; }
check_nothing

for f in $files; do
  # Far more lines than a pipe holds: a reader that stops at the first one must not read as "only the version".
  for _ in $(seq 1 3000); do echo "# a line that is not a version"; done >> "$f"
  check 1 "3000 other lines added to $f"
done
bump; echo "# one more line" >> apps/apple/project.yml; check 1 "the version, and one more line in project.yml"
bump; sed -i.bak -E 's/^( *minSdk = )[0-9]+/\11/' apps/android/app/build.gradle.kts; rm -f apps/android/app/build.gradle.kts.bak
grep -q 'minSdk = 1$' apps/android/app/build.gradle.kts || { echo "FAILED: build.gradle.kts has no minSdk line to change"; failed=1; }
check 1 "the version, and minSdk"
bump; echo "++ a line that looks like a file header" >> apps/apple/project.yml; check 1 "the version, and an added line that starts with '++ '"
printf -- '-- a line that looks like a file header\n' >> apps/apple/project.yml; git add -A; git commit -q -m "with a '-- ' line"
with="$(git rev-parse HEAD)"; sed -i.bak '$d' apps/apple/project.yml; rm -f apps/apple/project.yml.bak; git add -A; git commit -q -m removed
expect 1 "a removed line that starts with '-- '" "$with" HEAD
git reset -q --hard "$base"
chmod +x apps/apple/project.yml; check 1 "only the file's mode changed"
rm apps/apple/project.yml; ln -s ../bandroom/macos/project.yml apps/apple/project.yml; check 1 "a version file swapped for a symbolic link"
bump; echo "x" > apps/apple/extra.yml; check 1 "the version, and an added file"
git mv apps/apple/project.yml apps/apple/project-renamed.yml; check 1 "a version file renamed"
bump; echo "x" >> README.md; check 1 "the version, and another file"

exit "$failed"
