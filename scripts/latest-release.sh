#!/usr/bin/env bash
# PRODUCT-latest: a release that always holds a product's newest files under a tag that keeps its name, so a
# download link never names a version (docs/shared/dev/release.md):
#   https://github.com/OWNER/REPO/releases/tag/PRODUCT-latest
#   https://github.com/OWNER/REPO/releases/download/PRODUCT-latest/FILE
#
#   scripts/latest-release.sh PRODUCT TAG DIR   after TAG (PRODUCT-vX.Y.Z) is published: put DIR's files there and
#                                               point PRODUCT-latest at TAG's commit. The release workflow runs this.
#   scripts/latest-release.sh --highest PRODUCT TAG   succeeds when TAG is PRODUCT's highest full release (the
#                                               workflow asks before it marks a release as the repository's latest)
#   scripts/latest-release.sh --seed TAG        once, by the owner, before the first release of each product: make
#                                               every PRODUCT-latest from the files of TAG, a release of everything
#                                               together (v0.14.0), so the links work from the start
#
# The release is changed in place and never deleted, so a link keeps working while it is updated: the files are
# replaced one by one, then the tag is moved, then the words. Only a product's highest full release is put
# there: a run started again for an older tag, or a pre-release, leaves it alone.
# Needs gh, signed in with write access to the repository (GH_TOKEN in the workflow).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
die() { echo "$*" >&2; exit 1; }
repo=${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}

# put PRODUCT TAG DIR: the release PRODUCT-latest holds DIR's files and points at TAG's commit.
put() {
  local product=$1 tag=$2 dir=$3 latest="$1-latest" title sha have name
  title=$(scripts/release.sh --title "$product")
  sha=$(git rev-list -n 1 "$tag")
  local words="The files of [$title ${tag#"$product"-v}](https://github.com/$repo/releases/tag/$tag), under an address that stays the same from release to release. The notes are there."
  [ -n "$(ls "$dir")" ] || die "$dir holds no files for $latest"
  if gh release view "$latest" --repo "$repo" >/dev/null 2>&1; then
    gh release upload "$latest" --repo "$repo" --clobber "$dir"/*
    # A file the product no longer has must not stay behind as if it were its newest.
    have=$(gh release view "$latest" --repo "$repo" --json assets -q '.assets[].name')
    for name in $have; do
      [ -e "$dir/$name" ] || gh release delete-asset "$latest" "$name" --repo "$repo" --yes
    done
    gh api -X PATCH "repos/$repo/git/refs/tags/$latest" -f sha="$sha" -F force=true >/dev/null
    gh release edit "$latest" --repo "$repo" --title "$title: latest" --notes "$words" --latest=false
  else
    gh release create "$latest" --repo "$repo" --target "$sha" --latest=false --title "$title: latest" --notes "$words" "$dir"/*
  fi
  echo "$latest now holds the files of $tag"
}

# TAG is PRODUCT's highest full release (PRODUCT-vX.Y.Z, no pre-release): the one its latest follows.
highest() {
  local product=$1 tag=$2 top
  top=$(git tag --list "$product-v*" | grep -E "^$product-v[0-9]+\.[0-9]+\.[0-9]+\$" | sort -V | tail -1)
  [ "$tag" = "$top" ]
}

case "${1:-}" in
  --highest)
    [ $# -eq 3 ] || die "usage: scripts/latest-release.sh --highest PRODUCT TAG"
    highest "$2" "$3"
    ;;
  --seed)
    [ $# -eq 2 ] || die "usage: scripts/latest-release.sh --seed TAG"
    from=$2
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
    for product in $(scripts/release.sh --products); do
      mkdir "$tmp/$product"
      patterns=()
      while IFS= read -r f; do patterns+=(--pattern "$f"); done < <(scripts/release.sh --files "$product")
      gh release download "$from" --repo "$repo" --dir "$tmp/$product" "${patterns[@]}"
      (cd "$tmp/$product" && shasum -a 256 -- * > SHA256SUMS)
      put "$product" "$from" "$tmp/$product"
    done
    ;;
  ""|-*) die "usage: scripts/latest-release.sh PRODUCT TAG DIR | --highest PRODUCT TAG | --seed TAG" ;;
  *)
    [ $# -eq 3 ] || die "usage: scripts/latest-release.sh PRODUCT TAG DIR"
    product=$1 tag=$2 dir=$3
    if ! highest "$product" "$tag"; then
      echo "$tag is not $product's highest full release: $product-latest is left as it is"
      exit 0
    fi
    put "$product" "$tag" "$dir"
    ;;
esac
