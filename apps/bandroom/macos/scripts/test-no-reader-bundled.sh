#!/usr/bin/env bash
# Tests of check-no-reader-bundled.sh, the guard that keeps homr (AGPL-3.0) out of every build of Bandroom, on
# staged trees made here:
#   scripts/test-no-reader-bundled.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

fails=0 runs=0
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

# A staged workspace as the builds make it: the manifests, the engine and the adapters' own files.
staged() {
  local tree="$scratch/$1/workspace"
  mkdir -p "$tree/engine/src/scribe_engine" "$tree/ml/adapters/homr" "$tree/ml/adapters/separator"
  : > "$tree/pixi.toml"; : > "$tree/pixi.lock"; : > "$tree/engine/src/scribe_engine/cli.py"
  : > "$tree/ml/adapters/run_adapter.py"; : > "$tree/ml/adapters/homr/pyproject.toml"; : > "$tree/ml/adapters/homr/uv.lock"
  echo "$scratch/$1"
}

# expect <exit code> <what it is> <folder> [words its message must have]
expect() {
  local want=$1 what=$2 dir=$3 words=${4:-} got said
  said=$("$here/check-no-reader-bundled.sh" "$dir" 2>&1)
  got=$?
  runs=$((runs + 1))
  if [ "$got" != "$want" ]; then
    echo "FAIL: $what gave $got, expected $want: $said"
    fails=$((fails + 1))
  elif [ -n "$words" ] && ! printf '%s' "$said" | grep -q "$words"; then
    echo "FAIL: $what does not say '$words': $said"
    fails=$((fails + 1))
  fi
}

# Clean: the reader's own project files (ours, not homr's) are what a build carries.
clean=$(staged clean)
expect 0 "a clean staged workspace" "$clean"

# A Mac Bandroom that was run: the reader's environment is beside its project, inside the app.
ran=$(staged ran)
mkdir -p "$ran/workspace/ml/adapters/homr/.venv/lib/python3.12/site-packages/homr"
: > "$ran/workspace/ml/adapters/homr/.venv/pyvenv.cfg"
expect 1 "a workspace with the reader's .venv" "$ran" "AGPL-3.0"
expect 1 "a workspace with the reader's .venv" "$ran" "adapters/homr/.venv"

# Any adapter's environment: none of them belongs in a build, and the next one may be the reader's.
other=$(staged other)
mkdir -p "$other/workspace/ml/adapters/separator/.venv/bin"
expect 1 "a workspace with another adapter's .venv" "$other" "adapters/separator/.venv"

# The package itself, under whatever environment holds it: pixi's on Windows has no .venv in its path.
pixi=$(staged pixi)
mkdir -p "$pixi/workspace/.pixi/envs/homr/Lib/site-packages/homr/transformer"
: > "$pixi/workspace/.pixi/envs/homr/Lib/site-packages/homr/__init__.py"
expect 1 "a workspace with site-packages/homr" "$pixi" "site-packages/homr"
expect 1 "a workspace with site-packages/homr" "$pixi" "must not be in a build"

# A folder named homr that is not the package (the adapter's project folder) is fine; so is a file named .venv.
named=$(staged named)
mkdir -p "$named/workspace/site-packages-notes/homr"
: > "$named/workspace/ml/adapters/homr/.venv"
expect 0 "a workspace whose homr folder is the adapter's project" "$named"

# Nothing to check is not a pass.
expect 2 "a folder that is not there" "$scratch/nowhere" "no folder"

# The guard is only worth what calls it: the Mac stager, both release builds, and the Windows staging step's own check.
root="$(cd "$here/../../../.." && pwd)"
called() {
  local what=$1 file=$2 words=$3
  runs=$((runs + 1))
  if ! grep -qF -- "$words" "$root/$file"; then
    echo "FAIL: $what ($file) no longer has '$words'"
    fails=$((fails + 1))
  fi
}
called "the Mac stager" apps/bandroom/macos/scripts/stage-workspace.sh 'check-no-reader-bundled.sh" "$DEST"'
called "the Mac stager's empty start" apps/bandroom/macos/scripts/stage-workspace.sh 'rm -rf "$DEST"'
called "the Mac release build" .github/workflows/apple.yml 'scripts/check-no-reader-bundled.sh "$B"'
called "the Windows release build" .github/workflows/windows.yml 'check-no-reader-bundled.sh "$(cygpath -u "$RUNNER_TEMP")/publish/BrasscribeBandroom"'
called "the Windows staging step" apps/bandroom/windows/src/Brasscribe.Bandroom/Brasscribe.Bandroom.csproj '<_WsEnvironment Include="$(_Ws)**\.venv\**\*;$(_Ws)**\site-packages\homr\**\*" />'
called "the Windows staging step's stop" apps/bandroom/windows/src/Brasscribe.Bandroom/Brasscribe.Bandroom.csproj "<Error Condition=\"'@(_WsEnvironment)' != ''\""

echo "no-reader-bundled: $((runs - fails)) of $runs passed"
[ "$fails" -eq 0 ]
