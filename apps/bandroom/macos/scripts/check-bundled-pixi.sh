#!/usr/bin/env bash
# Stops when a pixi binary is older than the engine workspace asks for (requires-pixi in pixi.toml).
# Bandroom runs the engine with the pixi it bundles; one that is too old refuses the workspace and the
# engine never starts.
#
#   check-bundled-pixi.sh <path to pixi> [<path to pixi.toml>]
set -euo pipefail

pixi="${1:?usage: check-bundled-pixi.sh <path to pixi> [<path to pixi.toml>]}"
manifest="${2:-$(cd "$(dirname "$0")/../../../.." && pwd)/pixi.toml}"

need=$(sed -nE 's/^requires-pixi[[:space:]]*=[[:space:]]*">=[[:space:]]*([0-9][0-9.]*)".*/\1/p' "$manifest" | head -1)
[ -n "$need" ] || { echo "check-bundled-pixi: no 'requires-pixi = \">=X\"' in $manifest" >&2; exit 1; }
have=$("$pixi" --version | sed -nE 's/^pixi[[:space:]]+([0-9][0-9.]*).*/\1/p')
[ -n "$have" ] || { echo "check-bundled-pixi: $pixi did not print a version" >&2; exit 1; }

lowest=$(printf '%s\n%s\n' "$need" "$have" | sort -t. -k1,1n -k2,2n -k3,3n | head -1)
if [ "$lowest" != "$need" ]; then
  echo "check-bundled-pixi: pixi $have is older than the $need the engine workspace requires" >&2
  exit 1
fi
echo "pixi $have satisfies >=$need"
