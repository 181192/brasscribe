#!/bin/bash
# Sweep the B♭ cornet's reading and placement ranges on the Rust path (the Mikkel repro layers)
# and count the solo-layer notes the lead writes in another octave. Edits instruments.rs
# temporarily and restores it on exit. Usage (repo root):
#   docs/plan/trumpet/sweep.sh 55,79,52,82 55,79,52,84 52,89,52,89     # reading_lo,hi,limit_lo,hi
# ASHEARD=1 needs the one-line best_shift hook described in trumpet.md §1.3.
set -euo pipefail
W=$(git rev-parse --show-toplevel)
T=$(mktemp -d)
F=$W/core/brasscribe-core/src/instruments.rs
cp "$F" "$T/instruments.rs.orig"
trap 'cp "$T/instruments.rs.orig" "$F"' EXIT
C=$(cd "$W/core/conformance" && python3 -c "from brasscribe_conformance.cases import mikkel_contour; print(mikkel_contour())")
for v in "$@"; do
  read -r rl rh ll lh <<<"${v//,/ }"
  cp "$T/instruments.rs.orig" "$F"
  sed -i '' "s/reading: Some((55, 79)), reading_limit: Some((52, 82))/reading: Some(($rl, $rh)), reading_limit: Some(($ll, $lh))/" "$F"
  (cd "$W/core" && cargo build -q --profile fast -p brasscribe-cli)
  o=$T/rs-$rl-$rh-$ll-$lh
  "$W/core/target/fast/brasscribe-core" arrange-layers --layers "$W/data/mikkel/repro/layers" --beats "$W/data/mikkel/repro/mix.beats" \
    --out "$o" --title "Mikkel — solo cornet & brass band (draft)" --solo-contour "$C"
  echo "reading ($rl,$rh) limit ($ll,$lh):"
  python3 "$W/docs/plan/trumpet/lead_octaves.py" "$o/brass-band.musicxml" "$o/composition.json"
done
