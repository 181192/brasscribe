"""The solo beat-model bench (brasscribe_eval.solo_beat_model_bench): its score and its suite's gate."""

import json

from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

from brasscribe_eval import solo_beat_model_bench as M
from brasscribe_eval import suites

# A 3/4 line, one note a beat, a beat every half second; the tracker's beat is a quarter.
REF = [{"pitch": 60 + k % 5, "onset": 0.5 * k, "offset": 0.5 * k + 0.4, "quarter": float(k)} for k in range(12)]


def _comp(beats_per_bar: int, shift_ticks: int = 0) -> Composition:
    notes = [Note(r["pitch"], 480 * k + shift_ticks, 480, 1.0, [], r["onset"], r["offset"]) for k, r in enumerate(REF)]
    return Composition("t", [Voice("solo", VoiceRole.MELODY, notes, layer="solo")], [Meter(0, beats_per_bar)], [KeySig(0, 0)],
                       [0.5 * k for k in range(13)], 0, 480)


def test_a_line_written_where_the_score_has_it_scores_full_marks():
    s = M.score_part(REF, "3/4", _comp(3))
    assert s["onset_f1"] == s["written_f1"] == s["bar_position_acc"] == s["meter_match"] == 1.0


def test_the_wrong_bar_or_bar_phase_costs_written_f1_not_onset_f1():
    four = M.score_part(REF, "3/4", _comp(4))
    assert four["onset_f1"] == 1.0 and four["meter_match"] == 0.0 and four["written_f1"] < 1.0
    late = M.score_part(REF, "3/4", _comp(3, 480))  # every note a beat late in the bar
    assert late["onset_f1"] == 1.0 and late["meter_match"] == 1.0 and late["written_f1"] == 0.0


def test_the_suite_skips_without_final0_beats_and_is_gated(tmp_path):
    r = suites.run_suite("solo-beat-model", data=tmp_path)
    assert r["status"] == "skipped" and M.SMALL in r["reason"]
    song = tmp_path / M.SMALL / "urmp" / "01_Piece"
    song.mkdir(parents=True)
    (song / "reference.json").write_text(json.dumps({"parts": {"1-tpt": "tpt"}, "notes": [], "time_sig": "4/4"}))
    for f in ("1-tpt.beats", "1-tpt-sw.mid", "1-tpt-bp.mid"):
        (song / f).write_text("")
    r = suites.run_suite("solo-beat-model", data=tmp_path)  # small0 beats only: skipped, naming the final0 folder
    assert r["status"] == "skipped" and M.FINAL in r["reason"]
    base = suites.load_baselines()["suites"]["solo-beat-model"]["metrics"]
    for set_name in M.SETS:
        assert base[f"{set_name}.parts"]["tolerance"] == 0
        for model in M.MODELS:
            assert all(f"{set_name}.{model}.{k}" in base for k in ("onset_f1", "written_f1", "bar_position_acc", "meter_match"))
