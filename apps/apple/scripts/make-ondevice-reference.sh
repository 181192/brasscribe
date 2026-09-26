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
ROOT=/Users/k/private/brasscribe
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
