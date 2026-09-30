#!/usr/bin/env bash
# Reference outputs for the on-device solo pipeline, from the Python tools the engine uses:
#   <out>/sw.mid            SwiftF0 adapter (DP note segmentation, 80 ms hold)
#   <out>/bp.mid            Basic Pitch adapter (defaults: onset 0.5, frame 0.3, 127.7 ms)
#   <out>/beats-small0.beats Beat This! small0, minimal postprocessing
#   <out>/logmel.f32        Beat This! log-mel frontend, float32 frames x 128, little endian
#   <out>/solo/             brasscribe_eval.arrange_solo with Basic Pitch standing in for MuScriptor
# Light models on a short clip: no GPU lock needed.
# Usage: scripts/make-ondevice-reference.sh clip.wav out-dir
set -euo pipefail
# the repository: BRASSCRIBE_REPO, else the checkout this script is in
ROOT="${BRASSCRIBE_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}"
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="$2"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
"$ROOT/ml/adapters/swift-f0/run.sh" "$IN" "$OUT/sw.mid"
"$ROOT/ml/adapters/basic-pitch/run.sh" "$IN" "$OUT/bp.mid"
uv run --project "$ROOT/ml/adapters/beat-this" python - "$IN" "$OUT" <<'PY'
import sys, numpy as np, torch
from beat_this.inference import Audio2Beats
from beat_this.preprocessing import load_audio
from beat_this.utils import save_beat_tsv
src, out = sys.argv[1], sys.argv[2]
a2b = Audio2Beats(checkpoint_path="small0", device="cpu", dbn=False)
sig, sr = load_audio(src)
spect = a2b.signal2spect(sig, sr)
spect.numpy().astype("<f4").tofile(f"{out}/logmel.f32")
beats, downs = a2b(sig, sr)
save_beat_tsv(beats, downs, f"{out}/beats-small0.beats")
print("logmel", tuple(spect.shape), "beats", len(beats), "downbeats", len(downs))
PY
(cd "$ROOT/eval" && uv run python -m brasscribe_eval.arrange_solo --beats "$OUT/beats-small0.beats" \
  --sw "$OUT/sw.mid" --mus "$OUT/bp.mid" --bp "$OUT/bp.mid" --out "$OUT/solo" --title Reference)
# The same inputs through the layered solo-with-band path the Rust core ports
# (brasscribe_eval.arrange_layers_song), with only the solo layer present.
L="$OUT/layers"; mkdir -p "$L"
cp "$OUT/sw.mid" "$L/solo-sw.mid"; cp "$OUT/bp.mid" "$L/solo-bp.mid"; cp "$OUT/bp.mid" "$L/solo-mus.mid"
"$ROOT/ml/adapters/swift-f0/contour.sh" "$IN" "$L/solo-sw.contour.npz"
(cd "$ROOT/eval" && uv run python -c "
import sys, pretty_midi
for name in ('bass-mus', 'orchestra-mus', 'drums-mus'):
    pretty_midi.PrettyMIDI().write(sys.argv[1] + '/' + name + '.mid')
" "$L")
(cd "$ROOT/eval" && uv run python -m brasscribe_eval.arrange_layers_song --layers "$L" --beats "$OUT/beats-small0.beats" \
  --out "$OUT/layered" --title Reference --no-render --lineup minimal)
