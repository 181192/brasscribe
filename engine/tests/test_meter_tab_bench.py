"""The meter benchmark of the tab profiles (brasscribe_eval.meter_tab_bench): its passages and its suite."""

from __future__ import annotations

import pytest

from brasscribe_eval import meter_tab_bench as M
from brasscribe_eval import suites


def test_each_passage_is_in_its_meter_and_the_same_every_time():
    for name, (instrument, _, kind, beats, right, bpm, root) in M.PASSAGES.items():
        notes = M.passage(name)
        assert notes == M.passage(name) and beats in right, name
        beat = 60 / bpm
        assert notes[0]["onset"] == pytest.approx(beats * beat)  # a bar's rest
        starts = sorted({round(n["onset"] / beat, 3) % beats for n in notes})
        assert starts[0] == 0 and all(0 <= s < beats for s in starts), name  # every bar starts on its first beat
        assert max(n["offset"] for n in notes) <= (M.BARS + 1) * beats * beat + 1e-6
        assert min(n["pitch"] for n in notes) >= (28 if instrument == "bass-4" else 40), name
    assert {v[3] for v in M.PASSAGES.values()} == {2, 3, 4, 5}  # as counted: 6/8 in two, 12/8 in four
    waltz = [n for n in M.passage("waltz-chords-3-4") if n["onset"] < 2 * 3 * 60 / 132.0 - 1e-6]
    assert [len([n for n in waltz if abs(n["onset"] - (3 + b) * 60 / 132.0) < 1e-6]) for b in range(3)] == [1, 3, 3]  # bass, chord, chord


def test_the_suite_skips_without_its_data_and_is_gated(tmp_path):
    r = suites.run_suite("meter-tab", data=tmp_path)
    assert r["status"] == "skipped" and "eval/meter-tab" in r["reason"]
    base = suites.load_baselines()["suites"]["meter-tab"]["metrics"]
    assert base["right_became_wrong"]["tolerance"] == 0 and base["right_became_wrong"]["higher_is_better"] is False
    assert {"tracked_ok", "meter_ok", "excerpts"} <= set(base)
