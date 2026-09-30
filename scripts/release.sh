#!/usr/bin/env bash
# Cuts a release: bumps the app versions, regenerates CHANGELOG.md, commits `chore(release): X.Y.Z`
# and tags vX.Y.Z. Pushing the tag starts .github/workflows/release.yml, which builds, signs and
# publishes everything. See docs/dev/release.md.
#   scripts/release.sh X.Y.Z           prepare the commit and the tag locally, then print the push
#   scripts/release.sh X.Y.Z --push    also push main and the tag
#   scripts/release.sh --preview       print the notes the next release would get
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
command -v git-cliff >/dev/null || { echo "needs git-cliff (brew install git-cliff)" >&2; exit 1; }

if [ "${1:-}" = --preview ]; then
  git fetch -q --tags origin
  exec git-cliff --unreleased --strip header
fi

version=${1:?usage: scripts/release.sh X.Y.Z [--push] | --preview}
push=${2:-}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be X.Y.Z, got $version" >&2; exit 2; }
tag="v$version"

[ "$(git branch --show-current)" = main ] || { echo "run this on main" >&2; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "the working tree has changes" >&2; exit 1; }
git fetch -q origin main --tags
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "main is not at origin/main; pull first" >&2; exit 1; }
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && { echo "$tag already exists" >&2; exit 1; }
# The release commit carries the committer's email into the public history: it must be the one the
# previous release was made with, so a clone with some other default identity can't slip in.
email=$(git config user.email || true)
previous=$(git log -1 --format=%ae --grep='^chore(release): ' || true)
if [ -z "$email" ] || { [ -n "$previous" ] && [ "$email" != "$previous" ] && [ "${RELEASE_NEW_IDENTITY:-}" != 1 ]; }; then
  echo "git user.email is '$email', the last release was made as '$previous'." >&2
  echo "Set this repository's email (git config user.email ...), or RELEASE_NEW_IDENTITY=1 if the change is intended." >&2
  exit 1
fi

# The new version must be higher than the current one.
gradle=apps/android/app/build.gradle.kts
current=$(sed -nE 's/^ *versionName = "([^"]+)".*/\1/p' "$gradle")
if [ "$version" = "$current" ] || [ "$(printf '%s\n%s\n' "$current" "$version" | sort -V | tail -1)" != "$version" ]; then
  echo "version $version is not higher than the current $current" >&2; exit 1
fi

# The build number goes up by one on every release; Android's versionCode is where it is kept.
build=$(( $(sed -nE 's/^ *versionCode = ([0-9]+).*/\1/p' "$gradle") + 1 ))
sed -i.bak -E "s/^( *versionCode = )[0-9]+/\1$build/; s/^( *versionName = )\"[^\"]*\"/\1\"$version\"/" "$gradle"
for y in apps/apple/project.yml apps/bandroom/macos/project.yml; do
  sed -i.bak -E "s/^( *MARKETING_VERSION: )\"[^\"]*\"/\1\"$version\"/; s/^( *CURRENT_PROJECT_VERSION: )\"[^\"]*\"/\1\"$build\"/" "$y"
done
rm -f "$gradle.bak" apps/apple/project.yml.bak apps/bandroom/macos/project.yml.bak

git-cliff --tag "$tag" -o CHANGELOG.md 2>/dev/null
git add "$gradle" apps/apple/project.yml apps/bandroom/macos/project.yml CHANGELOG.md
git diff --cached --stat
git commit -q -m "chore(release): $version"
git tag "$tag"
echo "Release notes for $tag:"
git-cliff --latest --strip header 2>/dev/null

if [ "$push" = --push ]; then
  git push -q --atomic origin main "$tag"
  echo "Pushed. The release workflow is building $tag: gh run list -w release -L 1"
else
  echo "Ready. Push to start the release: git push --atomic origin main $tag"
fi
