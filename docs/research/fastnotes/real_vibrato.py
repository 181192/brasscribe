"""Real trumpet vibrato must stay one note: Iowa MIS "Trumpet.vib.ff" sustains, dry and in a measured hall.

Source: Iowa MIS "Trumpet.vib.ff.*" from https://theremin.music.uiowa.edu/MIS-Pitches-2012/MISBbTrumpet2012.html
(sounds/fetch.py skips them; the 16 kHz dry and hall renders are kept in data/eval/fast-notes-vibrato).

Counts the notes (after the line filter) that SwiftF0 segmentation makes of each sustained
vibrato note, at several pitch holds, and writes each case as a WAV for later adversarial runs.
Any note beyond one is a false note (for a trill detector: a false trill).

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/real_vibrato.py [--out DIR] [--holds 80,40,20]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from swift_f0 import SwiftF0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "data" / "sounds" / "raw" / "iowa-mis" / "trumpet-vib" / "pitch"
RENDERS = ROOT / "data" / "eval" / "fast-notes-vibrato"  # the rendered inputs (vib-<midi>-{dry,hall}.wav), kept after the raw set was removed
IR = ROOT / "data" / "sounds" / "raw" / "openair" / "usina-del-arte-symphony-hall" / "stereo" / "usina_main_s2_p3.wav"
NAMES = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
SR = 16000


def midi_of(name):
    m = re.search(r"\.([A-G]b?)(\d)\.", name)
    return 12 * (int(m.group(2)) + 1) + NAMES[m.group(1)]


def load(p):
    y, sr = sf.read(p, always_2d=True)
    y = y.mean(axis=1)
    n = int(len(y) * SR / sr)
    return np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y).astype(np.float32)


def convolve(y, ir):
    L = len(y) + len(ir)
    out = np.fft.irfft(np.fft.rfft(y, 2 * L) * np.fft.rfft(ir, 2 * L), 2 * L)[: len(y) + len(ir) // 4]
    return (out / np.max(np.abs(out)) * 0.8).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--holds", default="80,40,20")
    args = ap.parse_args()
    holds = [float(h) for h in args.holds.split(",")]
    det = SwiftF0()
    ir = load(IR)
    totals = {(env, h): [0, 0] for env in ("dry", "hall") for h in holds}
    print("sample | midi | " + " | ".join(f"{env} h{int(h)}" for env in ("dry", "hall") for h in holds))
    for p in sorted(SAMPLES.glob("*.aif*")):
        midi = midi_of(p.name)
        dry = load(p)
        cells = []
        for env, y in (("dry", dry), ("hall", convolve(dry, ir))):
            if args.out:
                args.out.mkdir(parents=True, exist_ok=True)
                sf.write(args.out / f"vib-{midi}-{env}.wav", y, SR)
            for h in holds:
                ln = probe.line(probe.notes_of(y, det, h))
                on_pitch = [n for n in ln if abs(n[2] - midi) <= 2]
                extra = len(ln) - 1
                totals[(env, h)][0] += max(extra, 0)
                totals[(env, h)][1] += 1
                cells.append(f"{len(ln)} ({len(on_pitch)} near)")
        print(f"{p.name} | {midi} | " + " | ".join(cells), flush=True)
    print("\nextra notes per sustained vibrato note: " + ", ".join(
        f"{env} h{int(h)} = {t[0] / t[1]:.2f}" for (env, h), t in totals.items()))


if __name__ == "__main__":
    main()
