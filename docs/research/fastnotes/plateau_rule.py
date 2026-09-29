"""Would a "3 frames within ±35 c of another semitone" split rule fire on vibrato?

Applies the plateau test from the fast-notes plan (F1: a new pitch is a run of >= MIN_FRAMES contour frames
within ±TOL cents of a semitone other than the note's own) to one-note material that must never split:

  - the 35 real Iowa MIS trumpet vibrato sustains, dry and in a measured hall (as real_vibrato.py);
  - synthetic vibrato: centred and one-sided (below the note, the usual lip/jaw vibrato on brass),
    at several widths and rates, dry and in the hall.

Reports, per case, the number of foreign-semitone plateaus and how many of them alternate A-B-A (the
pattern F1 splits at 3 frames). Any plateau is a false split; an A-B-A run is a false trill.

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/plateau_rule.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from swift_f0 import SwiftF0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402
import real_vibrato as rv  # noqa: E402

TOL, MIN_FRAMES, CONF = 0.35, 3, 0.5


def plateaus(midi, conf, own):
    """Runs of >= MIN_FRAMES confident frames within TOL of one semitone; returns their semitones."""
    near = np.round(midi)
    ok = (np.abs(midi - near) <= TOL) & (conf > CONF)
    runs, cur, n = [], None, 0
    for k, o in zip(near, ok):
        s = int(k) if o else None
        if s == cur and s is not None:
            n += 1
            continue
        if cur is not None and n >= MIN_FRAMES:
            runs.append(cur)
        cur, n = s, 1
    if cur is not None and n >= MIN_FRAMES:
        runs.append(cur)
    foreign = sum(r != own for r in runs)
    aba = sum(1 for a, b, c in zip(runs, runs[1:], runs[2:]) if a == c == own and b != own)
    return foreign, aba


def contour(y, det, lead=0.35, tail=0.3):
    r = det.detect(y, probe.SR)
    m = 69 + 12 * np.log2(np.maximum(r.pitch_hz, 1e-3) / 440)
    return r.timestamps, m, r.confidence


def tuned(t, m, c, a, b):
    sel = (t >= a) & (t <= b) & (c > CONF)
    off = np.angle(np.mean(np.exp(2j * np.pi * m[sel]))) / (2 * np.pi)  # circular mean of the fractional part
    return m - off


def main():
    det = SwiftF0()
    ir = rv.load(rv.IR)
    print("real Iowa vibrato (35 notes): foreign plateaus / A-B-A runs")
    for env in ("dry", "hall"):
        tot_f = tot_a = hit = 0
        for p in sorted(rv.SAMPLES.glob("*.aif*")):
            own = rv.midi_of(p.name)
            y = rv.load(p)
            if env == "hall":
                y = rv.convolve(y, ir)
            t, m, c = contour(y, det)
            voiced = t[(c > CONF) & (np.abs(m - own) < 2)]
            if len(voiced) < 10:
                continue
            a, b = voiced[0] + 0.15, voiced[-1] - 0.1  # skip the attack and the release
            mm = tuned(t, m, c, a, b)
            sel = (t >= a) & (t <= b)
            f, ab = plateaus(mm[sel], c[sel], own)
            tot_f += f
            tot_a += ab
            hit += f > 0
        print(f"  {env}: notes with a foreign plateau {hit}/35, plateaus {tot_f}, A-B-A {tot_a}")

    print("\nsynthetic 2 s vibrato on G4: foreign plateaus / A-B-A runs (dry | hall)")
    for cents, hz, one_sided in [(60, 5.5, False), (100, 6, False), (120, 6, False), (150, 7, False),
                                 (60, 5.5, True), (100, 5.5, True), (120, 6, True)]:
        cells = []
        for env in ("dry", "hall"):
            pt, amp, _ = probe.long_note(67, 2.0, vib_cents=cents / 2 if one_sided else cents, vib_hz=hz)
            if one_sided:  # swing from the note down to -cents
                pt = pt - (cents / 200) * (amp > 0)
            y = probe.render(pt, amp, reverb=2.0 if env == "hall" else 0.0)
            t, m, c = contour(y, det)
            sel = (t >= 0.8) & (t <= 2.2)
            mm = tuned(t, m, c, 0.8, 2.2) if not one_sided else m  # a one-sided vibrato has no centre on the note
            f, ab = plateaus(mm[sel], c[sel], 67)
            cells.append(f"{f}/{ab}")
        print(f"  {'one-sided' if one_sided else 'centred'} {'-' if one_sided else '±'}{cents if one_sided else cents} c {hz} Hz: "
              + " | ".join(cells))


if __name__ == "__main__":
    main()
