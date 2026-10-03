#!/usr/bin/env bash
# Stops when a pixi binary, or the pixi version CI pins (.pixi-version at the repository root), doesn't meet
# what the engine workspace asks for (requires-pixi in pixi.toml). Bandroom runs the engine with the pixi it
# bundles; one the workspace doesn't accept refuses it and the engine never starts.
#
#   check-bundled-pixi.sh <path to pixi> [<path to pixi.toml>]
#
# requires-pixi is read in full: ranges, upper bounds, `,` and `|`, `==`, `!=`, `~=` and `.*`
# (pixi-spec.awk; its tests are test-pixi-spec.sh).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
pixi="${1:?usage: check-bundled-pixi.sh <path to pixi> [<path to pixi.toml>]}"
manifest="${2:-$root/pixi.toml}"

spec=$(sed -nE "s/^requires-pixi[[:space:]]*=[[:space:]]*[\"']([^\"']*)[\"'].*/\1/p" "$manifest" | head -1)
[ -n "$spec" ] || { echo "check-bundled-pixi: no requires-pixi in $manifest" >&2; exit 1; }

meets() { awk -v spec="$spec" -v version="$1" -f "$here/pixi-spec.awk"; }

pinned=$(tr -d ' \r\n' < "$root/.pixi-version")
pinned="${pinned#v}"
if ! meets "$pinned"; then
  echo "check-bundled-pixi: the pinned pixi $pinned (.pixi-version) doesn't meet requires-pixi '$spec' in $manifest" >&2
  exit 1
fi

have=$("$pixi" --version | sed -nE 's/^pixi[[:space:]]+([0-9][0-9A-Za-z.+-]*).*/\1/p')
[ -n "$have" ] || { echo "check-bundled-pixi: $pixi did not print a version" >&2; exit 1; }
if ! meets "$have"; then
  echo "check-bundled-pixi: pixi $have doesn't meet requires-pixi '$spec' that the engine workspace asks for" >&2
  exit 1
fi
[ "$have" = "$pinned" ] || echo "check-bundled-pixi: note: pixi $have is not the pinned $pinned (.pixi-version)" >&2
echo "pixi $have meets '$spec' (pinned: $pinned)"
