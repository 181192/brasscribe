"""Unit-level fixtures from the Python reference on seeded synthetic inputs.

    uv run python -m brasscribe_conformance.fixtures

Writes core/brasscribe-core/tests/fixtures/*.json; `cargo test` compares the
Rust functions with them (exact equality). No recorded data is involved.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
from music21 import duration as m21duration

from brasscribe_music.quantize import choose_level, fill_gaps, quantize
from brasscribe_music.spelling import key_of, spell

from .cases import REPO

OUT = REPO / "core" / "brasscribe-core" / "tests" / "fixtures"
warnings.filterwarnings("ignore")


def spelling_cases(rng) -> list[dict]:
    cases = []
    for k in range(120):
        n = int(rng.integers(1, 400))
        # tonal-ish material: a random scale plus chromatic passing notes
        tonic = int(rng.integers(0, 12))
        scale = [(tonic + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)]
        pcs = [scale[i] if rng.random() > 0.2 else int(rng.integers(0, 12)) for i in rng.integers(0, 7, size=n)]
        pitches = [int(12 * rng.integers(3, 7) + pc) for pc in pcs]
        ticks = np.sort(rng.integers(0, 24 * 64, size=n)) // int(rng.choice([1, 6, 8, 12]))
        onsets = [float(t) / 24 for t in ticks]
        durs = [float(rng.integers(1, 97)) / 24 for _ in range(n)]
        sp = spell(onsets, durs, pitches)
        name, fifths = key_of(onsets, durs, pitches)
        cases.append({"onsets": onsets, "durations": durs, "pitches": pitches,
                      "spelled": [[s, a, o] for s, a, o in sp], "key": name, "fifths": fifths})
    return cases


def quantize_cases(rng) -> list[dict]:
    cases = []
    for k in range(80):
        nb = int(rng.integers(4, 200))
        ibi = rng.uniform(0.35, 1.3) * rng.uniform(0.9, 1.1, size=nb)
        beats = np.cumsum(ibi) + rng.uniform(0, 2)
        n = int(rng.integers(1, 300))
        on = np.sort(rng.uniform(beats[0] - 1, beats[-1] + 1, size=n))
        off = on + rng.uniform(0.03, 2.0, size=n)
        notes = [{"pitch": int(p), "onset": float(a), "offset": float(b)} for p, a, b in
                 zip(rng.integers(30, 90, size=n), on, off)]
        mono, auto = bool(k % 2), bool(k % 3)
        q = quantize(notes, beats, monophonic=mono, auto_level=auto)
        g = fill_gaps([type(x)(**vars(x)) for x in q], 12, 0.0)
        cases.append({"beats": beats.tolist(), "notes": notes, "monophonic": mono, "auto_level": auto,
                      "level": choose_level(beats, on).tolist(),
                      "quantized": [[x.pitch, x.start, x.end] for x in q],
                      "filled": [[x.pitch, x.start, x.end] for x in g]})
    return cases


def argsort_cases(rng) -> list[dict]:
    out = []
    for k in range(200):
        a = rng.integers(20, 100, size=int(rng.integers(1, 600))).astype(np.int32)
        out.append({"values": a.tolist(), "argsort": np.argsort(a).tolist()})
    return out


def duration_cases() -> list[dict]:
    out = []
    for den in (24, 48, 60, 72):
        for num in range(1, 8 * den + 1):
            ql = num / den
            qc = m21duration.quarterConversion(ql)
            t = qc.tuplet
            out.append({"num": num, "den": den,
                        "components": [[c.type, c.dots] for c in qc.components],
                        "tuplet": None if t is None else [t.numberNotesActual, t.numberNotesNormal,
                                                          t.durationNormal.type, t.durationNormal.dots]})
    return out


def freetime_cases_exact(rng) -> list[dict]:
    """Same as freetime_cases, recording which tempo onsets were passed."""
    from brasscribe_music.freetime import local_tempo, plan_free_time, unstable_runs

    out = []
    for k in range(150):
        nb = int(rng.integers(8, 160))
        ref = rng.uniform(0.35, 0.9)
        ibi = ref * rng.uniform(0.93, 1.07, size=nb)
        for _ in range(int(rng.integers(0, 3))):
            a = int(rng.integers(0, nb))
            n = len(ibi[a:a + int(rng.integers(2, 9))])
            ibi[a:a + n] = rng.uniform(1.0, 6.0, size=n)
        if rng.random() < 0.2:
            i = int(rng.integers(0, nb - 1))
            ibi[i], ibi[i + 1] = ref * 0.4, ref * 0.6
        t = np.cumsum(ibi) + rng.uniform(0, 3)
        bpb = int(rng.choice([2, 3, 4, 6]))
        first = int(rng.integers(0, bpb))
        on = np.sort(rng.uniform(t[0] - 1.5, t[-1], size=int(rng.integers(1, 400))))
        tempo_on = on[:: int(rng.integers(1, 4))] if rng.random() < 0.7 else None
        mode = rng.random()
        downs = None if mode < 0.5 else (((np.arange(len(t)) - first) % bpb == 0) if mode < 0.8 else rng.random(len(t)) < 0.25)
        tempo = float(rng.uniform(40, 110)) if rng.random() < 0.2 else None
        p = plan_free_time(t, on, bpb, first, downs, tempo=tempo, tempo_onsets=tempo_on)
        out.append({
            "t": t.tolist(), "onsets": on.tolist(), "tempo_onsets": None if tempo_on is None else tempo_on.tolist(),
            "bpb": bpb, "first": first, "downbeats": None if downs is None else [bool(x) for x in downs], "tempo": tempo,
            "runs": [list(map(int, r)) for r in unstable_runs(t)],
            "local_tempo": local_tempo(on, float(t[0]), float(t[-1])),
            "plan": {"beat_times": np.asarray(p.beat_times).tolist(), "first_downbeat": int(p.first_downbeat),
                     "spans": [[int(a), int(b), float(s0), float(s1), float(bpm)] for a, b, s0, s1, bpm in p.spans],
                     "notation": p.notation.value,
                     "regions": [[r.start, r.end, r.start_s, r.end_s, r.tempo_bpm] for r in p.regions(first)]},
        })
    return out


def durations_cases(rng) -> list[dict]:
    from brasscribe_music.durations import SEPARATED_STEM, Contour, contour_offsets, written_durations
    from brasscribe_music.quantize import BeatMap, QNote

    out = []
    for k in range(120):
        # a contour: frames every 16 ms, a melody of held and detached notes with dropouts
        n_frames = int(rng.integers(50, 900))
        t = np.arange(n_frames) * 0.016 + rng.uniform(0, 0.02)
        hz = np.zeros(n_frames)
        db = rng.uniform(-120, -60, size=n_frames)
        notes = []
        i = int(rng.integers(0, 20))
        while i < n_frames - 5:
            p = int(rng.integers(50, 85))
            length = int(rng.integers(3, 120))
            f = 440.0 * 2 ** ((p - 69 + rng.uniform(-0.3, 0.3, size=min(length, n_frames - i))) / 12)
            if rng.random() < 0.1:
                f = f * 2  # octave error
            hz[i:i + length] = f
            db[i:i + length] = rng.uniform(-40, -5) - np.linspace(0, rng.uniform(0, 90), len(f))
            holes = rng.random(len(f)) < 0.05
            hz[i:i + length][holes] = 0
            notes.append((float(t[i] + rng.uniform(-0.02, 0.02)), p))
            i += length + int(rng.integers(0, 40))
        midi = np.where(hz > 0, 69 + 12 * np.log2(np.where(hz > 0, hz, 1.0) / 440.0), np.nan)
        c = Contour(t, midi, db)
        settings = SEPARATED_STEM if k % 2 else {}
        ends = contour_offsets(c, notes, **settings)
        # written durations of a quantized voice from those notes
        beats = np.cumsum(rng.uniform(0.4, 0.8, size=max(4, len(t) // 30))) + t[0] - 0.5
        q, pos = [], 0
        for (on, p), e in zip(notes, ends):
            pos += int(rng.choice([6, 8, 12, 18, 24, 36, 48]))
            q.append(QNote(p, pos, pos + int(rng.choice([6, 12, 24])), on, float(e)))
        use_bm = bool(k % 3)
        w = written_durations(q, BeatMap(beats) if use_bm else None) if q else []
        out.append({"t": t.tolist(), "hz": hz.tolist(), "db": db.tolist(), "midi": [None if np.isnan(x) else x for x in midi],
                    "notes": [[o, p] for o, p in notes], "separated": bool(settings), "ends": [float(e) for e in ends],
                    "beats": beats.tolist(), "use_beat_map": use_bm,
                    "qnotes": [[x.pitch, x.start, x.end, x.onset_s, x.offset_s] for x in q],
                    "written": [[int(x.dur), float(x.performed), bool(x.staccato)] for x in w]})
    return out


def meter_cases(rng) -> list[dict]:
    """Solo meter on synthetic beat tracks: labels on (almost) every beat, jittered tempo, an inserted
    and a missed beat, accents on the true downbeats of 2, 3 or 4 beats per bar."""
    from brasscribe_music.beats import labels_on, solo_meter, track_bar_phase

    out = []
    for _ in range(60):
        meter = int(rng.choice([2, 3, 4]))
        n = int(rng.integers(24, 64))
        ibi = float(rng.uniform(0.35, 0.8))
        t = np.cumsum(np.r_[rng.uniform(0, 1), ibi * (1 + rng.normal(0, 0.03, n - 1))])
        phase0 = int(rng.integers(0, meter))
        strong = (np.arange(n) - phase0) % meter == 0
        on, du = [], []
        for k in range(n):
            if rng.random() < 0.85:
                on.append(t[k] + rng.normal(0, 0.01))
                du.append(ibi * (rng.uniform(0.8, 1.9) if strong[k] else rng.uniform(0.2, 0.7)))
            if rng.random() < 0.3:
                on.append(t[k] + ibi * float(rng.choice([0.5, 1 / 3])))
                du.append(ibi * 0.3)
        pos = np.where(rng.random(n) < 0.85, 1, rng.integers(1, meter + 1, n))
        pos[strong] = 1
        if rng.random() < 0.5:
            k = int(rng.integers(3, n - 3))
            t = np.insert(t, k, (t[k - 1] + t[k]) / 2)
            pos = np.insert(pos, k, 1)
        if rng.random() < 0.5:
            k = int(rng.integers(3, len(t) - 3))
            t, pos = np.delete(t, k), np.delete(pos, k)
        on, du = np.array(on), np.array(du)
        grid = t * float(rng.choice([1.0, 1.0, 1.001]))
        gp = labels_on(grid, t, pos)
        m = solo_meter(grid, gp == 1, gp, 1, 0, on, du)
        tb, first = track_bar_phase(t, (pos == 1).astype(float), meter)
        out.append({"t": t.tolist(), "pos": pos.tolist(), "grid": grid.tolist(), "onsets": on.tolist(),
                    "durations": du.tolist(), "grid_pos": gp.tolist(),
                    "meter": [int(m.beats_per_bar), int(m.first_downbeat), bool(m.from_labels), bool(m.compound),
                              float(m.strength), None if m.times is None else [float(x) for x in m.times]],
                    "track": [meter, [float(x) for x in tb], int(first)]})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260925)
    for name, data in (("spelling", spelling_cases(rng)), ("quantize", quantize_cases(rng)),
                       ("argsort", argsort_cases(rng)), ("duration", duration_cases()),
                       ("freetime", freetime_cases_exact(rng)), ("durations", durations_cases(rng)),
                       ("meter", meter_cases(rng))):
        (OUT / f"{name}.json").write_text(json.dumps(data))
        print(name, len(data))


if __name__ == "__main__":
    main()
