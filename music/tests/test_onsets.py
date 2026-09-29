"""Pitch-change onsets from the contour: trills and runs split, vibrato, bends and octave flips do not."""

import numpy as np

from brasscribe_music.durations import Contour
from brasscribe_music.onsets import FRAME, contour_notes, octave_flips


def contour(pitch: np.ndarray, confidence: bool = True) -> Contour:
    t = np.arange(len(pitch)) * FRAME
    return Contour(t, pitch.astype(float), np.zeros(len(pitch)), np.full(len(pitch), 0.9) if confidence else None)


def note(p: int, a: float, b: float) -> dict:
    return {"pitch": p, "onset": a, "offset": b}


def test_slurred_trill_splits_into_its_notes():
    frames = 5  # 80 ms a note: 12.5 notes/s
    pitch = 67 + 2 * ((np.arange(120) // frames) % 2) + 0.03
    for conf in (True, False):  # the phone's contour has no confidence
        out = contour_notes([note(67, 0.0, 120 * FRAME)], contour(pitch, conf))
        assert [n["pitch"] for n in out[:6]] == [67, 69, 67, 69, 67, 69]
        assert len(out) == 24 and all(n.get("split") for n in out)


def test_semitone_trill_needs_many_changes():
    pitch = 67 + 1 * ((np.arange(120) // 5) % 2).astype(float)
    assert len(contour_notes([note(67, 0.0, 120 * FRAME)], contour(pitch))) == 24
    # one neighbour swing (a lip vibrato touching the semitone below) is not a trill
    swing = np.full(120, 67.0)
    swing[50:56] = 66.0
    assert len(contour_notes([note(67, 0.0, 120 * FRAME)], contour(swing))) == 1


def test_vibrato_stays_one_note():
    t = np.arange(150) * FRAME
    for depth in (0.6, 1.0, 1.5):
        for one_sided in (False, True):
            v = np.sin(2 * np.pi * 5.5 * t) if not one_sided else -(1 - np.cos(2 * np.pi * 5.5 * t)) / 2
            out = contour_notes([note(70, 0.0, 150 * FRAME)], contour(70 + depth * v))
            assert len(out) == 1, (depth, one_sided)


def test_scale_run_splits():
    steps = np.array([0, 2, 4, 5, 7, 9, 11, 12])
    pitch = 62 + steps[np.arange(64) // 8].astype(float)
    out = contour_notes([note(62, 0.0, 64 * FRAME)], contour(pitch))
    assert [n["pitch"] for n in out] == list(62 + steps)


def test_rip_into_a_note_is_its_attack():
    pitch = np.r_[np.linspace(65, 71.6, 6), np.full(40, 72.0)]
    c = contour(pitch)
    out = contour_notes([note(68, 0.0, 6 * FRAME), note(72, 6 * FRAME, 46 * FRAME)], c)
    assert [(n["pitch"], n["onset"]) for n in out] == [(72, 0.0)]


def test_octave_flips_fold_unless_confirmed():
    notes = [note(72, 0.0, 0.2), note(84, 0.2, 0.35), note(72, 0.35, 0.8)]
    assert [n["pitch"] for n in octave_flips(notes)] == [72]
    assert [n["pitch"] for n in octave_flips(notes, [note(84, 0.21, 0.35)])] == [72, 84, 72]
    held = [note(60, 0.0, 1.0), note(72, 1.0, 2.0), note(60, 2.0, 3.0)]  # a slurred octave between held notes
    assert octave_flips(held) == held
