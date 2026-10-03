#!/usr/bin/env bash
# Tests of pixi-spec.awk, the reader of requires-pixi that check-bundled-pixi.sh uses:
#   scripts/test-pixi-spec.sh    (AWK=gawk or AWK=mawk tests another awk)
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

fails=0 runs=0
# expect <0 meets | 1 doesn't | 2 unreadable> <spec> <version>
expect() {
  local want=$1 spec=$2 version=$3 got
  "${AWK:-awk}" -v spec="$spec" -v version="$version" -f "$here/pixi-spec.awk" 2>/dev/null
  got=$?
  runs=$((runs + 1))
  if [ "$got" != "$want" ]; then
    echo "FAIL: '$spec' with $version gave $got, expected $want"
    fails=$((fails + 1))
  fi
}

# Lower bounds, as pixi.toml has it.
expect 0 '>=0.80' 0.81.0
expect 0 '>=0.80' 0.80.0
expect 0 '>=0.80' 0.80
expect 1 '>=0.80' 0.79.0
expect 1 '>=0.80' 0.9.0          # numeric parts, not text: 9 < 80
expect 0 '>=0.80' 1.0.0
expect 0 '>0.80' 0.80.1
expect 1 '>0.80' 0.80.0
# Upper bounds and ranges, `,` separated, with or without spaces.
expect 0 '<1' 0.81.0
expect 1 '<1' 1.0.0
expect 0 '<=0.81' 0.81.0
expect 1 '<=0.81' 0.81.1
expect 0 '>=0.80,<0.90' 0.81.0
expect 1 '>=0.80,<0.90' 0.90.0
expect 1 '>=0.80,<0.90' 0.79.9
expect 0 '>=0.80, <0.90' 0.85.2
expect 0 ' >= 0.80 , < 0.90 ' 0.85.2
# Exact versions and exclusions.
expect 0 '==0.81.0' 0.81.0
expect 0 '==0.81' 0.81.0
expect 1 '==0.81.0' 0.81.1
expect 0 '0.81.0' 0.81.0
expect 1 '0.81.0' 0.81.1
expect 1 '>=0.80,!=0.81.0' 0.81.0
expect 0 '>=0.80,!=0.81.0' 0.81.1
# Series: `.*`, and conda's `=1.2`.
expect 0 '0.81.*' 0.81.3
expect 1 '0.81.*' 0.82.0
expect 0 '==0.81.*' 0.81.0
expect 0 '=0.81' 0.81.4
expect 1 '=0.81' 0.810.0
expect 1 '!=0.81.*' 0.81.2
expect 0 '!=0.81.*' 0.80.9
expect 0 '*' 0.1.0
# Compatible release.
expect 0 '~=0.80' 0.95.0
expect 1 '~=0.80' 1.0.0
expect 1 '~=0.80' 0.79.0
expect 0 '~=0.80.1' 0.80.5
expect 1 '~=0.80.1' 0.81.0
expect 1 '~=0.80.1' 0.80.0
# Alternatives.
expect 0 '<0.70|>=0.80' 0.81.0
expect 0 '<0.70|>=0.80' 0.65.0
expect 1 '<0.70|>=0.80' 0.75.0
# Versions as pixi and tags print them.
expect 0 '>=0.80' v0.81.0
expect 0 '>=0.80' 0.81.0rc1
# Specs that can't be read stop the check instead of passing.
expect 2 '' 0.81.0
expect 2 '>=' 0.81.0
expect 2 '>=0.80,' 0.81.0
expect 2 '=>0.80' 0.81.0
expect 2 '>=0.8*' 0.81.0
expect 2 '>=0.80.*' 0.81.0
expect 2 '~=1' 1.2.0
expect 2 '>=abc' 0.81.0
expect 2 '>=0.80' nonsense
expect 2 '|' 0.81.0
expect 2 '>=0.90|' 0.81.0
expect 2 '|>=0.90' 0.81.0
expect 2 '<0.70||>=0.80' 0.81.0

# check-bundled-pixi.sh: a pre-release pixi is refused, whatever the spec says; a release that meets it passes.
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
printf '[workspace]\nrequires-pixi = ">=0.80"\n' > "$scratch/pixi.toml"
fake() { printf '#!/bin/sh\necho "pixi %s"\n' "$1" > "$scratch/pixi-$1"; chmod +x "$scratch/pixi-$1"; echo "$scratch/pixi-$1"; }
check() {
  local want=$1 version=$2 got
  "$here/check-bundled-pixi.sh" "$(fake "$version")" "$scratch/pixi.toml" > /dev/null 2>&1
  got=$?
  runs=$((runs + 1))
  if [ "$got" != "$want" ]; then
    echo "FAIL: check-bundled-pixi.sh with pixi $version gave $got, expected $want"
    fails=$((fails + 1))
  fi
}
check 0 0.81.0
check 1 0.79.0
check 1 0.81.0rc1
check 1 0.82.0-beta.1

echo "pixi-spec: $((runs - fails)) of $runs passed"
[ "$fails" -eq 0 ]
