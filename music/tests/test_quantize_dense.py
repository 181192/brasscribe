"""Dense quantization of a monophonic line (fast runs, trills): no note lost to a shared slot, readable grids."""

import numpy as np

from brasscribe_music.quantize import choose_grids, choose_grids_dense, quantize


def run(bpm: float, per_beat: int, n: int, jitter: float = 0.0, seed: int = 0, start_beat: int = 2):
    spb = 60 / bpm
    beats = np.arange(0, 16) * spb + 0.5
    rng = np.random.default_rng(seed)
    on = beats[start_beat] + np.arange(n) * spb / per_beat + rng.uniform(-jitter, jitter, n)
    notes = [{"pitch": 60 + (k % 2), "onset": float(t), "offset": float(t + 0.8 * spb / per_beat)} for k, t in enumerate(on)]
    return notes, beats


def test_sextuplets_and_32nds_keep_every_note():
    for per_beat, bpm in ((6, 100), (8, 96), (3, 100)):
        notes, beats = run(bpm, per_beat, 24)
        assert len(quantize(notes, beats, monophonic=True, auto_level=False)) < 24  # the old path loses notes
        q = quantize(notes, beats, monophonic=True, auto_level=False, dense=True)
        assert len(q) == 24
        assert {x.start % (24 // per_beat) for x in q} == {0}, (per_beat, [x.start for x in q])


def test_sixteenths_with_jitter_stay_sixteenths():
    notes, beats = run(140, 4, 32, jitter=0.02, seed=3)
    q = quantize(notes, beats, monophonic=True, auto_level=False, dense=True)
    assert all(x.start % 6 == 0 for x in q)


def test_beats_that_hold_their_onsets_choose_as_before():
    rng = np.random.default_rng(7)
    for _ in range(50):
        on = np.sort(rng.uniform(0, 30, 40))
        base, dense = choose_grids(on), choose_grids_dense(on, None, np.full(40, 0.5))
        for k, g in base.items():
            f = np.array([x - k for x in on if int(np.floor(x + 1 / 12)) == k])
            if len(np.unique(np.round(f * g))) == len(f) and not np.any(np.round(f * g) == g):
                assert dense[k] == g


def test_no_32nds_on_a_doubled_beat():
    # beats 0.25 s apart (a doubled 120 BPM grid): 8 per beat would be 64ths of 31 ms
    beats = np.arange(0, 20) * 0.25
    on = beats[4] + np.arange(8) * 0.25 / 8
    g = choose_grids_dense(on * 0 + np.arange(8) / 8 + 4, None, np.full(20, 0.25))
    assert g[4] != 8
    notes = [{"pitch": 60, "onset": float(t), "offset": float(t + 0.02)} for t in on]
    q = quantize(notes, beats, monophonic=True, auto_level=False, dense=True)
    assert all((x.start % 24) % 3 == 0 or (x.start % 24) % 4 == 0 for x in q)


def test_one_grid_through_a_run():
    notes, beats = run(120, 6, 36, jitter=0.008, seed=1)
    q = quantize(notes, beats, monophonic=True, auto_level=False, dense=True)
    assert len(q) == 36
    assert all(x.start % 4 == 0 for x in q)  # every beat of the sextuplet run on the sextuplet grid


def test_rubato_sixteenths_keep_one_grid():
    bpm, div, n = 100, 4, 32
    beat = 60 / bpm
    t, on = 1.0, []
    for i in range(n):
        on.append(t)
        t += beat * (1 + 0.10 * np.sin(2 * np.pi * (i / div) / 4)) / div
    notes = [{"pitch": 60 + i % 5, "onset": o, "offset": o + 0.8 * beat / div, "confidence": 1.0} for i, o in enumerate(on)]
    bt = np.arange(1.0 - 4 * beat, 1.0 + 40 * beat, beat)
    q = quantize(notes, bt, monophonic=True, auto_level=False, dense=True)
    assert {x.start % 24 for x in q} <= {0, 6, 12, 18}
