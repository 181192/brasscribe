"""Reference note events of upstream Basic Pitch for BasicPitchParityTest.

Runs `basic_pitch.inference.predict` with its defaults on the batch-1 ONNX export
(models/converted/basic-pitch/nmp-b1.onnx, ONNX Runtime CPU), exactly as convert/basic-pitch/parity.py
does, on:

- the synthetic melody of SyntheticMelody (same formula) generated at 22050 Hz and written as a float
  WAV, so librosa loads it unchanged;
- 30 s of the URMP trumpet part data/urmp/Dataset/10_March_tpt_sax/AuSep_1_tpt_10_March.wav, loaded
  (and resampled from 48 kHz with soxr_hq) by librosa as predict does.

Run with the Basic Pitch conversion env (it has onnxruntime and basic-pitch 0.4):
    convert/basic-pitch/.venv/bin/python apps/android/pitch/src/test/python/make_basic_pitch_reference.py
"""

import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from basic_pitch import inference

ROOT = Path(__file__).resolve().parents[6]
MODEL = ROOT / "models/converted/basic-pitch/nmp-b1.onnx"
URMP = ROOT / "data/urmp/Dataset/10_March_tpt_sax/AuSep_1_tpt_10_March.wav"
OUT = Path(__file__).resolve().parents[1] / "resources"

NOTES = [(70, 0.8), (72, 0.4), (74, 0.4), (75, 1.2), (0, 0.3), (77, 0.6), (79, 0.6), (81, 0.3), (82, 1.6), (0, 0.5),
         (65, 0.9), (67, 0.45), (69, 0.45), (70, 2.0), (0, 0.4)] * 3


def melody(sr: int) -> np.ndarray:
    out = []
    for pitch, dur in NOTES:
        n = int(round(dur * sr))
        if pitch == 0:
            out.append(np.zeros(n, dtype=np.float32))
            continue
        f0 = 440.0 * 2.0 ** ((pitch - 69) / 12.0)
        t = np.arange(n, dtype=np.float64) / sr
        tone = sum((1.0 / h) * np.sin(2 * math.pi * f0 * h * t) for h in range(1, 7))
        env = np.minimum(1.0, np.minimum(t / 0.02, (dur - t) / 0.02))
        out.append((0.25 * tone * env).astype(np.float32))
    return np.concatenate(out)


def run(path: Path) -> list[dict]:
    model = inference.Model(str(MODEL))
    _, _, events = inference.predict(str(path), model)
    return [{"start": round(float(s), 5), "end": round(float(e), 5), "pitch": int(p), "amplitude": round(float(a), 5)}
            for s, e, p, a, _ in sorted(events, key=lambda x: (x[0], x[2]))]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "synthetic.wav"
        audio = melody(22050)
        sf.write(wav, audio, 22050, subtype="FLOAT")
        ref = {"samples": int(len(audio)), "notes": run(wav)}
        (OUT / "basic-pitch-synthetic.json").write_text(json.dumps(ref))
        print(f"synthetic: {len(ref['notes'])} notes")
        if URMP.exists():
            clip = Path(tmp) / "urmp.wav"
            x, sr = sf.read(URMP, dtype="float32", frames=30 * 48000)
            sf.write(clip, x, sr, subtype="FLOAT")
            ref = {"source": str(URMP.relative_to(ROOT)), "seconds": 30, "notes": run(clip)}
            (OUT / "basic-pitch-urmp-march.json").write_text(json.dumps(ref))
            print(f"urmp: {len(ref['notes'])} notes")
        else:
            print("URMP clip not present, skipped", file=sys.stderr)


if __name__ == "__main__":
    main()
