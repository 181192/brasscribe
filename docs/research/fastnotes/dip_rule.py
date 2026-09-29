"""Would a "6 dB loudness dip between two peaks >= 50 ms apart" re-tongue rule fire on sustained vibrato?

Applies the articulation test from the fast-notes plan (F1: the same pitch re-tongued is a loudness dip of at
least DIP dB between two peaks at least GAP s apart) to the SwiftF0 loudness of one-note material:
the 35 real Iowa MIS trumpet vibrato sustains, dry and in a measured hall. Every dip found is a false
repeated note.

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/dip_rule.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from swift_f0 import SwiftF0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import real_vibrato as rv  # noqa: E402

DIP, GAP, CONF = 6.0, 0.05, 0.5


def dips(t, db, dip=DIP, gap=GAP):
    """Count troughs >= dip below both neighbouring local peaks, the peaks >= gap apart."""
    n = 0
    peaks = [i for i in range(1, len(db) - 1) if db[i] >= db[i - 1] and db[i] >= db[i + 1]]
    for a, b in zip(peaks, peaks[1:]):
        if t[b] - t[a] < gap:
            continue
        low = db[a:b + 1].min()
        if min(db[a], db[b]) - low >= dip:
            n += 1
    return n


def main():
    det = SwiftF0()
    ir = rv.load(rv.IR)
    for env in ("dry", "hall"):
        found, notes, worst = 0, 0, []
        for p in sorted(rv.SAMPLES.glob("*.aif*")):
            own = rv.midi_of(p.name)
            y = rv.load(p)
            if env == "hall":
                y = rv.convolve(y, ir)
            r = det.detect(y, rv.SR)
            m = 69 + 12 * np.log2(np.maximum(r.pitch_hz, 1e-3) / 440)
            v = r.timestamps[(r.confidence > CONF) & (np.abs(m - own) < 2)]
            if len(v) < 10:
                continue
            sel = (r.timestamps >= v[0] + 0.1) & (r.timestamps <= v[-1] - 0.15)
            k = dips(r.timestamps[sel], r.loudness_db[sel])
            found += k
            notes += 1
            if k:
                worst.append((p.name.split(".")[3], k))
        print(f"{env}: false re-tongues {found} on {notes} sustained notes; {worst}")
    for dip in (3.0, 4.5):
        print(f"(at {dip} dB the dry count would be", end=" ")
        tot = 0
        for p in sorted(rv.SAMPLES.glob("*.aif*")):
            own = rv.midi_of(p.name)
            r = det.detect(rv.load(p), rv.SR)
            m = 69 + 12 * np.log2(np.maximum(r.pitch_hz, 1e-3) / 440)
            v = r.timestamps[(r.confidence > CONF) & (np.abs(m - own) < 2)]
            if len(v) < 10:
                continue
            sel = (r.timestamps >= v[0] + 0.1) & (r.timestamps <= v[-1] - 0.15)
            tot += dips(r.timestamps[sel], r.loudness_db[sel], dip=dip)
        print(f"{tot})")


if __name__ == "__main__":
    main()
