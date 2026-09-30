#!/usr/bin/env bash
# Cuts a release in two steps, because main only takes changes through pull requests
# (docs/dev/release.md):
#   scripts/release.sh --preview      print the notes the next release would get
#   scripts/release.sh X.Y.Z          bump every app version, regenerate CHANGELOG.md, commit
#                                     `chore(release): X.Y.Z` on release/vX.Y.Z and open a pull request
#   scripts/release.sh --tag X.Y.Z    after that pull request is merged: tag the merged commit on
#                                     main as vX.Y.Z and push the tag, which starts the release workflow
# Pre-releases (vX.Y.Z-beta.N) are tagged by hand on main; this script makes only X.Y.Z.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
for tool in git-cliff gh; do
  command -v "$tool" >/dev/null || { echo "needs $tool (brew install $tool)" >&2; exit 1; }
done
# git-cliff looks up pull requests and contributors on GitHub; authenticated, it isn't rate-limited.
export GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}"
# The release notes of a stable version span every change since the previous stable version, so
# pre-release tags are ignored.
cliff=(git-cliff --ignore-tags '.*-.*')

die() { echo "$*" >&2; exit 1; }
semver='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'

on_fresh_main() {
  [ "$(git branch --show-current)" = main ] || die "run this on main"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "the working tree has changes"
  git fetch -q origin main --tags
  [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || die "main is not at origin/main; pull first"
}

case "${1:-}" in
  --preview)
    git fetch -q --tags origin
    exec "${cliff[@]}" --unreleased --strip header
    ;;
  --tag)
    version=${2:?usage: scripts/release.sh --tag X.Y.Z}
    [[ $version =~ $semver ]] || die "version must be X.Y.Z, got $version"
    tag="v$version"
    on_fresh_main
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null && die "$tag already exists"
    # The release commit as merged (rebase, squash or merge commit all keep its subject).
    commit=$(git log -1 --format=%H --first-parent --grep="^chore(release): $version\$" main; \
             git log -1 --format=%H --grep="^chore(release): $version\$" main)
    commit=$(head -1 <<<"$commit")
    [ -n "$commit" ] || die "no 'chore(release): $version' commit on main; merge the release pull request and pull first"
    git tag "$tag" "$commit"
    git push -q origin "$tag"
    echo "Pushed $tag. The release workflow is building it: gh run list -w release -L 1"
    exit 0
    ;;
  ""|-*) die "usage: scripts/release.sh X.Y.Z | --tag X.Y.Z | --preview" ;;
esac

version=$1
[[ $version =~ $semver ]] || die "version must be X.Y.Z (no leading zeros), got $version"
tag="v$version"
branch="release/$tag"
on_fresh_main
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && die "$tag already exists"
git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1 && die "$branch already exists on origin"

# The release commit carries the author's and committer's email into the public history: both must
# be the email the previous release was authored with, so a clone with another default identity (or
# a GIT_AUTHOR_EMAIL in the environment) can't slip in. The previous release's author is the
# reference, not its committer: GitHub becomes the committer when it merges the release pull request.
previous=$(git log -1 --format=%ae --grep='^chore(release): ' || true)
for who in GIT_AUTHOR_IDENT GIT_COMMITTER_IDENT; do
  email=$(git var "$who" | sed -E 's/.*<([^>]*)>.*/\1/')
  if [ -z "$email" ] || { [ -n "$previous" ] && [ "$email" != "$previous" ] && [ "${RELEASE_NEW_IDENTITY:-}" != 1 ]; }; then
    die "the ${who%_IDENT} email is '$email', the last release was made as '$previous'.
Set this repository's email (git config user.email ...), or RELEASE_NEW_IDENTITY=1 if the change is intended."
  fi
done

# The new version must be higher than the current one.
gradle=apps/android/app/build.gradle.kts
current=$(sed -nE 's/^ *versionName = "([^"]+)".*/\1/p' "$gradle")
[[ $current =~ $semver ]] || die "can't read the current version from $gradle (got '$current')"
IFS=. read -r a1 a2 a3 <<<"$current"; IFS=. read -r b1 b2 b3 <<<"$version"
if (( b1 < a1 || (b1 == a1 && (b2 < a2 || (b2 == a2 && b3 <= a3))) )); then
  die "version $version is not higher than the current $current"
fi

# Notes and changelog first: if git-cliff fails, nothing has been changed yet.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
"${cliff[@]}" --tag "$tag" -o "$tmp/CHANGELOG.md"
"${cliff[@]}" --unreleased --tag "$tag" --strip header -o "$tmp/notes.md"

# The build number goes up by one on every release; Android's versionCode is where it is kept.
build=$(( $(sed -nE 's/^ *versionCode = ([0-9]+).*/\1/p' "$gradle") + 1 ))
apple="apps/apple/project.yml apps/bandroom/macos/project.yml"
windows="apps/windows/Directory.Build.props apps/bandroom/windows/Directory.Build.props"
sed -i.bak -E "s/^( *versionCode = )[0-9]+/\1$build/; s/^( *versionName = )\"[^\"]*\"/\1\"$version\"/" "$gradle"
for y in $apple; do
  sed -i.bak -E "s/^( *MARKETING_VERSION: )\"[^\"]*\"/\1\"$version\"/; s/^( *CURRENT_PROJECT_VERSION: )\"[^\"]*\"/\1\"$build\"/" "$y"
done
for x in $windows; do
  sed -i.bak -E "s#<Version>[^<]*</Version>#<Version>$version</Version>#" "$x"
done
for f in $gradle $apple $windows; do rm -f "$f.bak"; done

# A sed that matches nothing still succeeds: check every file really has the new version.
{ grep -q "versionName = \"$version\"" "$gradle" && grep -q "versionCode = $build" "$gradle"; } || die "$gradle was not bumped"
for y in $apple; do
  { grep -q "MARKETING_VERSION: \"$version\"" "$y" && grep -q "CURRENT_PROJECT_VERSION: \"$build\"" "$y"; } || die "$y was not bumped"
done
for x in $windows; do grep -q "<Version>$version</Version>" "$x" || die "$x was not bumped"; done

mv "$tmp/CHANGELOG.md" CHANGELOG.md
git switch -q -c "$branch"
git add $gradle $apple $windows CHANGELOG.md
git diff --cached --stat
git commit -q -m "chore(release): $version"
git push -q -u origin "$branch"
gh pr create --base main --head "$branch" --title "chore(release): $version" --body-file - <<EOF
Release $version (build $build). After this is merged, tag it: \`scripts/release.sh --tag $version\`.

## Release notes

$(cat "$tmp/notes.md")
EOF
git switch -q main
echo "Merge the pull request, pull main, then: scripts/release.sh --tag $version"
