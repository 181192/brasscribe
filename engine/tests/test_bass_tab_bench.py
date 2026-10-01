"""The bass tab benchmark (brasscribe_eval.bass_tab_bench): its reference, its scores and its suite."""

from __future__ import annotations

import json

import numpy as np
import pytest

from brasscribe_eval import bass_tab_bench as B
from brasscribe_eval import suites

SR = 16000


def _tone(pitch: int, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    f = 440 * 2 ** ((pitch - 69) / 12)
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 7)) * np.exp(-2 * t)


def _stem(pitches: list[int], sounding: int) -> tuple[np.ndarray, list[dict]]:
    """A rendered line whose MIDI says `pitches` and whose sound is `sounding` semitones from them."""
    audio = np.concatenate([_tone(p + sounding, 0.5) for p in pitches])
    return audio, [{"pitch": p, "onset": 0.5 * i, "offset": 0.5 * i + 0.45} for i, p in enumerate(pitches)]


def test_the_reference_octave_is_read_from_the_sound_not_assumed():
    written = [40, 45, 47, 52, 43, 48, 50, 55]
    audio, notes = _stem(written, -12)
    assert B.sounding_shift(audio, SR, notes) == -12  # a bass patch: an octave below the MIDI
    audio, notes = _stem(written, 0)
    assert B.sounding_shift(audio, SR, notes) == 0  # an instrument that sounds as written
    assert B.sounding_shift(audio, SR, []) == 0


def _tab(notes: list[tuple], tempo: float = 120.0, beats: int = 4, violations: int = 0) -> dict:
    """notes: (pitch, onset, string, fret, confidence)."""
    return {"notes": [{"pitch": p, "onset_s": on, "offset_s": on + 0.4, "start": 24 * i, "dur": 8 if i == 2 else 24,
                       "string": s, "fret": f, "out_of_range": s is None, "confidence": c} for i, (p, on, s, f, c) in enumerate(notes)],
            "violations": [{"kind": "span-too-wide"}] * violations, "tempo_bpm": tempo, "meter": {"beats": beats, "beat_unit": 4}}


REF = {"notes": [{"pitch": p, "onset": 0.5 * i, "offset": 0.5 * i + 0.45} for i, p in enumerate([28, 33, 35, 40])],
       "tempo_bpm": 120.0, "beats_per_bar": 4}


def test_a_tab_that_matches_its_reference_scores_full_marks():
    s = B.score_tab(REF, _tab([(28, 0.0, 4, 0, 1.0), (33, 0.5, 4, 5, 1.0), (35, 1.01, 4, 7, 1.0), (40, 1.5, 3, 7, 1.0)]))
    assert s["onset_f1"] == 1.0 and s["octave_err_rate"] == 0.0 and s["out_of_range"] == 0.0 and s["violations"] == 0.0
    assert (s["tempo_ok"], s["tempo_ok_level"], s["meter_ok"]) == (1.0, 1.0, 1.0)
    assert s["hand_travel"] == 1.0  # frets 5, 7, 7: the open string does not move the hand
    assert s["high_fret_share"] == 0.0 and s["doubt_share"] == 0.0 and s["wrong"] == 0.0
    assert s["triplet_lengths"] == 0.25  # the third note: a triplet's length between notes on the 16th grid


def test_octave_errors_range_tempo_level_and_doubt_are_counted():
    tab = _tab([(28, 0.0, 4, 0, 0.9), (45, 0.5, 4, 17, 0.2), (35, 1.2, 4, 7, 0.3), (90, 1.5, None, None, 0.9)],
               tempo=60.0, beats=3, violations=2)
    s = B.score_tab(REF, tab)
    assert s["octave_err_rate"] == 0.25  # the A heard an octave high
    assert s["onset_r"] == 0.25 and s["out_of_range"] == 0.25 and s["violations"] == 2.0
    assert (s["tempo_ok"], s["tempo_ok_level"], s["meter_ok"]) == (0.0, 1.0, 0.0)  # half the tempo: the right pulse, another level
    assert s["high_fret_share"] == pytest.approx(1 / 3) and s["hand_travel"] == 10.0
    assert (s["wrong"], s["doubt_marked"], s["doubt_marked_wrong"]) == (3.0, 2.0, 2.0)
    without = B.score_tab({"notes": REF["notes"], "tempo_bpm": None, "beats_per_bar": None}, tab)
    assert "tempo_ok" not in without and "meter_ok" not in without  # a song whose tempo changes is not scored on it


def test_the_suite_skips_without_its_data_and_is_gated(tmp_path):
    r = suites.run_suite("bass-tab", data=tmp_path)
    assert r["status"] == "skipped" and "eval/slakh-bass" in r["reason"]
    base = suites.load_baselines()["suites"]["bass-tab"]["metrics"]
    for mode in B.MODES:
        assert base[f"{mode}.violations"] == {"value": 0, "tolerance": 0, "higher_is_better": False}
        assert f"{mode}.onset_f1" in base and f"{mode}.hand_travel" in base
    entry = tmp_path / "eval" / B.SET / "Track1"
    entry.mkdir(parents=True)
    (entry / "reference.json").write_text(json.dumps(REF))
    r = suites.run_suite("bass-tab", data=tmp_path)  # a reference without the models' outputs: still skipped, with the file
    assert r["status"] == "skipped" and ("song.beats" in r["reason"] or "brasscribe-core" in r["reason"])
