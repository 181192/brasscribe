"""Reference output of upstream SwiftF0 for the synthetic test melody used by SwiftF0ParityTest.

Run with the SwiftF0 adapter environment:
    ml/adapters/swift-f0/.venv/bin/python apps/android/pitch/src/test/python/make_reference.py

The melody is generated from a formula (see `melody` below and SyntheticMelody.kt), so no audio is
stored: both sides compute the same float32 samples.
"""

import json
import math
from pathlib import Path

import numpy as np
import swift_f0
from swift_f0.music import segment_notes

SR = 16000
# (MIDI pitch, seconds) pairs; 0 is silence. About 33 s, longer than one 30.3 s detection window.
NOTES = [(70, 0.8), (72, 0.4), (74, 0.4), (75, 1.2), (0, 0.3), (77, 0.6), (79, 0.6), (81, 0.3), (82, 1.6), (0, 0.5),
         (65, 0.9), (67, 0.45), (69, 0.45), (70, 2.0), (0, 0.4)] * 3


def melody() -> np.ndarray:
    out = []
    for pitch, dur in NOTES:
        n = int(round(dur * SR))
        if pitch == 0:
            out.append(np.zeros(n, dtype=np.float32))
            continue
        f0 = 440.0 * 2.0 ** ((pitch - 69) / 12.0)
        t = np.arange(n, dtype=np.float64) / SR
        tone = sum((1.0 / h) * np.sin(2 * math.pi * f0 * h * t) for h in range(1, 7))
        env = np.minimum(1.0, np.minimum(t / 0.02, (dur - t) / 0.02))
        out.append((0.25 * tone * env).astype(np.float32))
    return np.concatenate(out)


def main() -> None:
    audio = melody()
    det = swift_f0.SwiftF0(threads=1)
    res = det.detect(audio, SR)
    notes = segment_notes(res)
    ref = {
        "samples": int(len(audio)),
        "frames": int(len(res.pitch_hz)),
        "confidence": [round(float(c), 5) for c in res.confidence],
        "pitch_hz": [round(float(p), 3) for p in res.pitch_hz],
        "loudness_db": [round(float(x), 3) for x in res.loudness_db],
        "notes": [{"start": round(n.start, 4), "end": round(n.end, 4), "pitch_hz": round(n.pitch_hz, 3)} for n in notes],
    }
    out = Path(__file__).resolve().parents[1] / "resources" / "swiftf0-reference.json"
    out.write_text(json.dumps(ref))
    print(f"{len(audio)} samples, {len(res.pitch_hz)} frames, {len(notes)} notes -> {out}")


if __name__ == "__main__":
    main()
