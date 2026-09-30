#!/usr/bin/env bash
# Reference outputs for the band draft made on the device, from the tools the engine's brass-band profile
# runs with muscriptor=False (the same path as `brasscribe run <mix> brass-band --no-muscriptor`):
#   <out>/bp.mid             Basic Pitch adapter on the whole mix
#   <out>/beats-small0.beats Beat This! small0 adapter
#   <out>/minimal/           brasscribe_eval.arrange_song, Basic Pitch in the melody, bass and harmony slots
#   <out>/quartet/           the same for the quartet
# Light models: no GPU lock needed. The apps' parity tests read <out> from data/runs/apple/<name>-band-draft-ref.
# Usage: scripts/make-band-draft-reference.sh mix.wav out-dir
set -euo pipefail
# the repository: BRASSCRIBE_REPO, else the checkout this script is in
ROOT="${BRASSCRIBE_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}"
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="$2"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
"$ROOT/ml/adapters/basic-pitch/run.sh" "$IN" "$OUT/bp.mid"
BEAT_THIS_MODEL=small0 "$ROOT/ml/adapters/beat-this/run.sh" "$IN" "$OUT/beats-small0.beats"
for lineup in minimal quartet; do
  (cd "$ROOT/eval" && uv run python -m brasscribe_eval.arrange_song --beats "$OUT/beats-small0.beats" \
    --melody "$OUT/bp.mid" --bass "$OUT/bp.mid" --harmony "$OUT/bp.mid" --out "$OUT/$lineup" \
    --title Reference --no-render --lineup "$lineup")
done
