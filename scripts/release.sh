#!/usr/bin/env bash
# Cuts a release of one product in two steps, because main only takes changes through pull requests
# (docs/shared/dev/release.md):
#   scripts/release.sh --preview PRODUCT   print the notes the product's next release would get
#   scripts/release.sh PRODUCT X.Y.Z       bump the product's versions, add the release to its changelog, commit
#                                          `chore(release): PRODUCT X.Y.Z` on release/PRODUCT-vX.Y.Z and open a
#                                          pull request
#   scripts/release.sh --tag PRODUCT X.Y.Z after that pull request is merged: tag the merged commit on main as
#                                          PRODUCT-vX.Y.Z and push the tag, which starts the release workflow
#   scripts/release.sh --notes TAG         the notes of the release TAG (PRODUCT-vX.Y.Z), as the release
#                                          workflow publishes them; needs only git-cliff
#   scripts/release.sh --files PRODUCT     the files a release of the product holds, one per line
#   scripts/release.sh --products          the products, one per line
# Products: brasscribe (Play for Android, Mac, iPhone and iPad, Windows), fretscribe (the same four),
# bandroom (Bandroom for Mac and Windows, with the engine inside) and scribe-core (the command-line tool).
# Each has its own version, tags and changelog (changelogs/PRODUCT.md); CHANGELOG.md is the history up to the
# last release of everything together. Pre-releases (PRODUCT-vX.Y.Z-beta.N) are tagged by hand on main.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

die() { echo "$*" >&2; exit 1; }
semver='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
PRODUCTS="brasscribe fretscribe bandroom scribe-core"
usage="usage: scripts/release.sh PRODUCT X.Y.Z | --tag PRODUCT X.Y.Z | --preview PRODUCT | --notes TAG | --files PRODUCT | --products
products: $PRODUCTS"

# What a product is made of. The files are what its release holds (the release workflow publishes exactly
# these, and the apps', the site's and the READMEs' download links name them). The version files are the ones
# its builds read; the paths are what its notes are
# written from: its own code and the shared layers it is built from (as ci.yml's change detection has them).
product() {
  name=$1 gradle="" apple="" windows="" include=() exclude=() files=()
  local shared=("core/**" "design/tooling/**" "sounds/**" "apps/fixtures/**" "engine/openapi.json")
  case "$name" in
    brasscribe)
      title="Brasscribe Play"
      files=(brasscribe-play-android-arm64-v8a.apk brasscribe-play-android-universal.apk brasscribe-play-macos-arm64.zip
             brasscribe-play-ios-unsigned.ipa brasscribe-play-windows-x64.zip)
      gradle=apps/android/products/brasscribe/build.gradle.kts
      apple=apps/apple/products/brasscribe/project.yml
      windows=apps/windows/products/brasscribe/Kalli.Brasscribe/Kalli.Brasscribe.csproj
      include=("apps/android/**" "apps/apple/**" "apps/windows/**" "capture/**" "design/brands/brasscribe/**" "${shared[@]}")
      exclude=("apps/*/products/fretscribe/**" "apps/android/design/fretscribe/**") ;;
    fretscribe)
      title="Fretscribe"
      files=(fretscribe-android-arm64-v8a.apk fretscribe-android-universal.apk fretscribe-macos-arm64.zip
             fretscribe-ios-unsigned.ipa fretscribe-windows-x64.zip)
      gradle=apps/android/products/fretscribe/build.gradle.kts
      apple=apps/apple/products/fretscribe/project.yml
      windows=apps/windows/products/fretscribe/Kalli.Fretscribe/Kalli.Fretscribe.csproj
      include=("apps/android/**" "apps/apple/**" "apps/windows/**" "capture/**" "design/brands/fretscribe/**" "${shared[@]}")
      exclude=("apps/*/products/brasscribe/**" "apps/android/design/brasscribe/**") ;;
    bandroom)
      title="Bandroom"
      files=(brasscribe-bandroom-macos-arm64.zip brasscribe-bandroom-windows-x64.zip)
      apple=apps/bandroom/macos/project.yml
      windows=apps/bandroom/windows/Directory.Build.props
      include=("apps/bandroom/**" "engine/**" "music/**" "eval/**" "ml/**" "studio/**" "pixi.toml" "pixi.lock"
               "design/brands/brasscribe/**" "${shared[@]}") ;;
    scribe-core)
      # The core's Cargo version stays as it is (the fixtures carry it in their MusicXML): the tag is the version.
      title="scribe-core"
      files=(scribe-core-macos-arm64.tar.gz scribe-core-linux-x86_64.tar.gz scribe-core-windows-x86_64.zip)
      include=("core/**") ;;
    *) die "unknown product '$name'
$usage" ;;
  esac
  prefix="$name-v"
  changelog="changelogs/$name.md"
}

# git-cliff for the product: only its own tags are releases, only its paths are changes.
cliff() {
  local args=(--tag-pattern "^${prefix}[0-9]+\\.[0-9]+\\.[0-9]+\$") p
  for p in "${include[@]}"; do args+=(--include-path "$p"); done
  for p in ${exclude[@]+"${exclude[@]}"}; do args+=(--exclude-path "$p"); done
  git-cliff "${args[@]}" "$@"
}

# The product's last release before a commit (HEAD unless given): its own newest tag, and before it has one,
# the last release of everything together (vX.Y.Z), which every product was part of. Pre-releases are passed
# over, so a release's notes span every change since the last full release; `with_pre` counts them too.
previous_tag() {
  local from=${1:-HEAD} with_pre=${2:-}
  local own=(--match "${prefix}[0-9]*") all=(--match 'v[0-9]*')
  if [ -z "$with_pre" ]; then own+=(--exclude "${prefix}*-*"); all+=(--exclude '*-*'); fi
  git describe --tags --abbrev=0 "${own[@]}" "$from" 2>/dev/null \
    || git describe --tags --abbrev=0 "${all[@]}" "$from" 2>/dev/null || true
}

# The version of the product's last release: from its tag, or from the last release of everything.
previous_version() {
  local tag; tag=$(previous_tag)
  tag=${tag#"$prefix"}; echo "${tag#v}"
}

on_fresh_main() {
  # main is checked out in the main checkout only: a worktree (also the release worktree the builds are made in)
  # cannot be on it.
  [ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ] || die "run this in the main checkout, not in a worktree"
  [ "$(git branch --show-current)" = main ] || die "run this on main"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "the working tree has changes"
  git fetch -q origin main --tags
  [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || die "main is not at origin/main; pull first"
}

# git-cliff looks up pull requests and contributors on GitHub; authenticated, it isn't rate-limited.
export GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}"
case "${1:-}" in
  --products) for p in $PRODUCTS; do echo "$p"; done; exit 0 ;;
  --files)
    [ $# -eq 2 ] || die "$usage"
    product "$2"; printf '%s\n' "${files[@]}"; exit 0 ;;
  --title)
    [ $# -eq 2 ] || die "$usage"
    product "$2"; echo "$title"; exit 0 ;;
  --notes)
    # For the release workflow: the tag names the product, and the range is explicit, so a run started again
    # for an older tag gets that tag's notes. A pre-release counts from the release or pre-release before it.
    [ $# -eq 2 ] || die "$usage"
    tag=$2
    [[ $tag =~ ^(brasscribe|fretscribe|bandroom|scribe-core)-v([0-9]+\.[0-9]+\.[0-9]+)(-[0-9A-Za-z.-]+)?$ ]] \
      || die "not a release tag: $tag (PRODUCT-vX.Y.Z)"
    product "${BASH_REMATCH[1]}"
    command -v git-cliff >/dev/null || die "needs git-cliff"
    pre=${BASH_REMATCH[3]}
    prev=$(previous_tag "$tag^" "$pre")
    # The tag itself is the release the notes are for, whether or not it is a pre-release.
    args=(--tag-pattern "^(${prefix}[0-9]+\\.[0-9]+\\.[0-9]+(-[0-9A-Za-z.-]+)?|v[0-9]+\\.[0-9]+\\.[0-9]+)\$")
    for p in "${include[@]}"; do args+=(--include-path "$p"); done
    for p in ${exclude[@]+"${exclude[@]}"}; do args+=(--exclude-path "$p"); done
    # (RELEASE_OFFLINE=1 leaves out the links to pull requests, for a tag that is not on GitHub yet.)
    # --tag names the release: the tagged commit itself need not be one of the product's own changes.
    git-cliff "${args[@]}" ${RELEASE_OFFLINE:+--offline} --tag "$tag" --strip header "${prev:+$prev..}$tag"
    exit 0 ;;
esac
for tool in git-cliff gh; do
  command -v "$tool" >/dev/null || die "needs $tool (brew install $tool)"
done

case "${1:-}" in
  --preview)
    [ $# -eq 2 ] || die "$usage"
    product "$2"
    git fetch -q --tags origin
    prev=$(previous_tag)
    cliff ${prev:+"$prev..HEAD"} --unreleased --strip header
    exit
    ;;
  --tag)
    [ $# -eq 3 ] || die "$usage"
    product "$2"; version=$3
    [[ $version =~ $semver ]] || die "version must be X.Y.Z, got $version"
    tag="$prefix$version"
    on_fresh_main
    git rev-parse -q --verify "refs/tags/$tag" >/dev/null && die "$tag already exists"
    # The release commit as merged: rebase and squash put it on main's first-parent line; a merge
    # commit keeps it on the side, and then the merge commit itself is what main released.
    # A squash merge appends the pull request number to the subject: "chore(release): fretscribe X.Y.Z (#45)".
    commit=$(git log -1 --format=%H -E --grep="^chore\(release\): $name ${version//./\\.}( \(#[0-9]+\))?\$" main)
    [ -n "$commit" ] || die "no 'chore(release): $name $version' commit on main; merge the release pull request and pull first"
    # grep reads to the end (no -q): leaving early would end rev-list with a broken pipe, which
    # pipefail reports as "not found" once the history is longer than a pipe buffer.
    if ! git rev-list --first-parent main | grep -x "$commit" >/dev/null; then
      commit=$(git rev-list --first-parent --ancestry-path "$commit..main" | tail -1)
    fi
    git tag "$tag" "$commit"
    git push -q origin "$tag"
    echo "Pushed $tag. The release workflow is building it: gh run list -w release -L 1"
    exit 0
    ;;
  ""|-*) die "$usage" ;;
esac
[ $# -eq 2 ] || die "$usage"

product "$1"; version=$2
[[ $version =~ $semver ]] || die "version must be X.Y.Z (no leading zeros), got $version"
tag="$prefix$version"
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

# The new version must be higher than the product's last one. An Android app can only be installed over a
# lower versionCode, and its versionName has only ever gone up.
current=$(previous_version)
[[ $current =~ $semver ]] || die "can't read $name's last version from its tags (got '$current')"
IFS=. read -r a1 a2 a3 <<<"$current"; IFS=. read -r b1 b2 b3 <<<"$version"
if (( b1 < a1 || (b1 == a1 && (b2 < a2 || (b2 == a2 && b3 <= a3))) )); then
  die "version $version is not higher than $name's current $current"
fi

# Notes and changelog first: if git-cliff fails, nothing has been changed yet.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
prev=$(previous_tag)
cliff ${prev:+"$prev..HEAD"} --unreleased --tag "$tag" --strip header -o "$tmp/notes.md"
# The changelog is the product's own: this release on top of the ones before it, under the file's first lines.
head="# $title: changes

Every release of $title, newest first. Generated from the commit history by git-cliff (\`cliff.toml\`,
\`scripts/release.sh\`). The releases before $title had tags of its own are in [CHANGELOG.md](../CHANGELOG.md)."
{
  printf '%s\n\n' "$head"
  cat "$tmp/notes.md"
  if [ -f "$changelog" ]; then printf '\n'; sed -n '/^## /,$p' "$changelog"; fi
} > "$tmp/changelog.md"

# The build number goes up by one on every release of the product: Android's versionCode and Apple's build.
default_config='/^ *defaultConfig \{/,/^ *\}/'
bumped=()
if [ -n "$gradle" ]; then
  code=$(( $(sed -nE "$default_config"' s/^ *versionCode = ([0-9]+).*/\1/p' "$gradle") + 1 ))
  sed -i.bak -E "$default_config { s/^( *versionCode = )[0-9]+/\1$code/; s/^( *versionName = )\"[^\"]*\"/\1\"$version\"/; }" "$gradle"
  { grep -q "versionName = \"$version\"" "$gradle" && grep -q "versionCode = $code" "$gradle"; } || die "$gradle was not bumped"
  bumped+=("$gradle")
fi
if [ -n "$apple" ]; then
  build=$(( $(sed -nE 's/^ *CURRENT_PROJECT_VERSION: "([0-9]+)".*/\1/p' "$apple") + 1 ))
  sed -i.bak -E "s/^( *MARKETING_VERSION: )\"[^\"]*\"/\1\"$version\"/; s/^( *CURRENT_PROJECT_VERSION: )\"[^\"]*\"/\1\"$build\"/" "$apple"
  { grep -q "MARKETING_VERSION: \"$version\"" "$apple" && grep -q "CURRENT_PROJECT_VERSION: \"$build\"" "$apple"; } || die "$apple was not bumped"
  bumped+=("$apple")
fi
if [ -n "$windows" ]; then
  sed -i.bak -E "s#<Version>[^<]*</Version>#<Version>$version</Version>#" "$windows"
  grep -q "<Version>$version</Version>" "$windows" || die "$windows was not bumped"
  bumped+=("$windows")
fi
for f in ${bumped[@]+"${bumped[@]}"}; do rm -f "$f.bak"; done

mkdir -p "$(dirname "$changelog")"
mv "$tmp/changelog.md" "$changelog"
git switch -q -c "$branch"
git add ${bumped[@]+"${bumped[@]}"} "$changelog"
git diff --cached --stat
git commit -q -m "chore(release): $name $version"
git push -q -u origin "$branch"
gh pr create --base main --head "$branch" --title "chore(release): $name $version" --body-file - <<EOF
$title $version. After this is merged, tag it: \`scripts/release.sh --tag $name $version\`.

## Release notes

$(cat "$tmp/notes.md")
EOF
git switch -q main
echo "Merge the pull request, pull main, then: scripts/release.sh --tag $name $version"
