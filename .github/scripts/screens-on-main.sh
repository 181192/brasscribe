#!/usr/bin/env bash
# What changed in the screen catalogues' pictures between one ci run on main and the record before it.
#
#   .github/scripts/screens-on-main.sh RUN OUT
#
# RUN is a ci run; each of its catalogue jobs that passed left an artefact screens-<catalogue>-<commit> with its
# screenshots and record.json (the commit, the runner image and the toolchain they were taken with). For each, the
# nearest earlier ci run of the same kind that has a record of that catalogue is the one compared with, and only
# when its runner image and toolchain are the same: a new image is "no earlier record", not a difference. Nothing
# is rendered here; studio/catalogue/compare.mjs compares the two sets of pictures.
#
# OUT gets, for each catalogue with changed screens, <catalogue>/ (index.html with before, the difference and
# after; summary.md; the images), and issues/<platform>.md: what to say in that platform's issue, with
# ARTIFACT_URL where the link to OUT, uploaded, goes. summary.md in OUT says what was compared with what.
#
# Needs gh (GH_TOKEN with actions: read), jq, node, and studio's npm packages with Playwright's Chromium.
# BRANCH and EVENT (default main and push) say which runs are records: to try it on a branch's hand-started runs,
# BRANCH=<branch> EVENT=workflow_dispatch.
set -euo pipefail
run="$1" out="$2"
repo="${GITHUB_REPOSITORY:?}"
branch="${BRANCH:-main}" event="${EVENT:-push}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$out/issues"
: > "$out/summary.md"

say() { printf '%s\n' "$*" | tee -a "$out/summary.md"; }

platform() {
  case "$1" in
    android-*) echo Android ;;
    studio) echo Studio ;;
    *-mac) echo Mac ;;
    *-windows) echo Windows ;;
    *) echo Other ;;
  esac
}
title() {
  case "$1" in
    android-brasscribe) echo "Brasscribe for Android" ;;
    android-fretscribe) echo "Fretscribe for Android" ;;
    studio) echo "Studio" ;;
    play-mac) echo "Play for Mac" ;;
    bandroom-mac) echo "Bandroom for Mac" ;;
    play-windows) echo "Play for Windows" ;;
    bandroom-windows) echo "Bandroom for Windows" ;;
    *) echo "$1" ;;
  esac
}

# The artefacts of a run that are records: "<name> <id>" lines.
records() { gh api --paginate "repos/$repo/actions/runs/$1/artifacts?per_page=100" --jq '.artifacts[] | select(.expired | not) | select(.name | startswith("screens-")) | "\(.name) \(.id)"'; }

# An artefact's files into a folder.
fetch() {
  mkdir -p "$2"
  gh api "repos/$repo/actions/artifacts/$1/zip" > "$2.zip"
  unzip -q -o "$2.zip" -d "$2"
  rm -f "$2.zip"
}

# The pictures of a record, side by side in one folder: "home/light.png" as "home--light.png". Not the pictures a
# Windows catalogue keeps of screens it could not take, nor its scans.
flat() {
  mkdir -p "$2"
  (cd "$1" && find . -name '*.png' -not -path '*/not-taken/*' -not -path '*/scans/*' -not -path '*/results/*' | sed 's|^\./||') | while IFS= read -r f; do
    cp "$1/$f" "$2/${f//\//--}"
  done
}

info="$(gh api "repos/$repo/actions/runs/$run")"
sha="$(jq -r .head_sha <<< "$info")"
created="$(jq -r .created_at <<< "$info")"
say "Screens of ${sha:0:12} (run $run), compared with the record before each."
say ""

records "$run" > "$work/now.txt"
if [ ! -s "$work/now.txt" ]; then say "The run has no screen records: nothing to compare."; exit 0; fi

# Earlier runs of the same kind, newest first; their records are listed once, when first asked for.
gh api "repos/$repo/actions/workflows/ci.yml/runs?branch=$branch&event=$event&per_page=30" \
  --jq ".workflow_runs[] | select(.created_at < \"$created\") | \"\(.id) \(.head_sha)\"" > "$work/earlier.txt"

while read -r name id; do
  catalogue="${name#screens-}"; catalogue="${catalogue%-*}"
  fetch "$id" "$work/$catalogue/after-raw"
  if [ ! -f "$work/$catalogue/after-raw/record.json" ]; then
    say "- $(title "$catalogue"): its catalogue did not pass in this run, so it is not a record."
    continue
  fi
  with="$(jq -c '[.image, .toolchain]' "$work/$catalogue/after-raw/record.json")"
  before="" why="no earlier record"
  while read -r earlier earlier_sha; do
    [ -f "$work/run-$earlier.txt" ] || records "$earlier" > "$work/run-$earlier.txt"
    earlier_id="$(awk -v n="screens-$catalogue-$earlier_sha" '$1 == n { print $2 }' "$work/run-$earlier.txt")"
    [ -n "$earlier_id" ] || continue
    fetch "$earlier_id" "$work/$catalogue/before-raw"
    if [ ! -f "$work/$catalogue/before-raw/record.json" ]; then rm -rf "$work/$catalogue/before-raw"; continue; fi
    if [ "$(jq -c '[.image, .toolchain]' "$work/$catalogue/before-raw/record.json")" = "$with" ]; then
      before="$earlier_sha"
    else
      why="the record before it, ${earlier_sha:0:12}, was taken with another runner image or toolchain"
    fi
    break
  done < "$work/earlier.txt"
  if [ -z "$before" ]; then
    say "- $(title "$catalogue"): not compared ($why)."
    continue
  fi
  flat "$work/$catalogue/before-raw" "$work/$catalogue/before"
  flat "$work/$catalogue/after-raw" "$work/$catalogue/after"
  report="$out/$catalogue"
  rm -rf "$report"; mkdir -p "$report"
  (cd "$root/studio" && node catalogue/compare.mjs "$work/$catalogue/before" "$work/$catalogue/after" "$report" > /dev/null) || true
  if [ ! -f "$report/result.json" ]; then
    say "- $(title "$catalogue"): the comparison with ${before:0:12} could not run."
    rm -rf "$report"
    continue
  fi
  if [ "$(jq -r .any "$report/result.json")" != true ]; then
    say "- $(title "$catalogue"): the same as at ${before:0:12} ($(jq -r .screens "$report/result.json") screens)."
    rm -rf "$report"
    continue
  fi
  say "- $(title "$catalogue"): screens changed since ${before:0:12} (see $catalogue/index.html)."
  {
    printf '### %s, since %s\n\n' "$(title "$catalogue")" "${before:0:12}"
    cat "$report/summary.md"
    printf '\nBefore, the difference and after: %s/index.html in ARTIFACT_URL\n\n' "$catalogue"
  } >> "$work/issue-$(platform "$catalogue").md"
done < "$work/now.txt"

for body in "$work"/issue-*.md; do
  [ -f "$body" ] || continue
  p="${body##*/issue-}"; p="${p%.md}"
  {
    printf 'The screen catalogue'"'"'s pictures on main at %s differ from the record before it. ' "$sha"
    printf 'Nothing waited for this: look at the pictures, and close the issue when the change is the one that was meant.\n\n'
    cat "$body"
  } > "$out/issues/$p.md"
done
