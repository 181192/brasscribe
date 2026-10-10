"""The benchmark gate (brasscribe_eval.suites) and the benches it runs: failures and gaps never pass as results."""

import json
import math
from pathlib import Path

import numpy as np

from brasscribe_eval import suites


def _report(value, higher_is_better=True):
    baselines = {"tolerance": 0.01, "suites": {"s": {"metrics": {"m": {"value": 0.5, "higher_is_better": higher_is_better}}}}}
    return suites.gate([{"suite": "s", "status": "ran", "metrics": {"m": value}}], baselines, allow_improved=True)


def test_a_nan_metric_is_missing_not_improved():
    for higher in (True, False):
        report = _report(math.nan, higher)
        assert report["suites"][0]["checks"][0]["status"] == "missing"
        assert not report["passed"]
    assert _report(0.7)["passed"]  # a real improvement still passes with allow_improved


def test_a_suite_that_exits_is_an_error_and_the_run_goes_on(monkeypatch):
    def exits(data, mode):
        raise SystemExit("missing contour")

    monkeypatch.setitem(suites.SUITES, "exits", suites.Suite("exits", "", exits))
    r = suites.run_suite("exits", data=Path("."))
    assert r["status"] == "error" and "missing contour" in r["reason"]


def test_a_crashing_clip_is_counted_not_scored_as_perfect(monkeypatch):
    from brasscribe_eval import fast_notes_bench as B

    def crash(*args, **kwargs):
        raise ValueError("under two beats")

    monkeypatch.setattr(B, "run_clip", crash)
    errors: dict = {}
    B.evaluate(beats=("oracle",), only="ctl-ampvib-i0-t100-s1-tongue-room", errors=errors)
    assert errors == {"oracle": 1}


def test_solo_vote_reads_the_given_data_directory(tmp_path):
    from brasscribe_eval import solo_vote_bench as B

    note = {"pitch": 60, "onset": 0.0, "offset": 0.5}
    song = tmp_path / "eval" / "choralebricks-brass4" / "song"
    song.mkdir(parents=True)
    (song / "reference.json").write_text(json.dumps([{**note, "part": "S"}, {**note, "part": "A"}]))
    for t, part in (("Track00006", "S02-Trumpet"), ("Track00014", "S00-Trumpet")):
        (tmp_path / "eval" / "slakh-trumpet" / t).mkdir(parents=True)
        (tmp_path / "eval" / "slakh-trumpet" / t / "reference.json").write_text(json.dumps([{**note, "part": part}]))
    cases = B.cases(tmp_path)
    assert [(name, stems.parent) for name, stems, _ in cases] == [
        ("chorale:song", tmp_path / "mega53-out-bench"), ("slakh:Track00006", tmp_path / "mega53-out-bench"),
        ("slakh:Track00014", tmp_path / "mega53-out-bench")]
    assert [len(ref) for *_, ref in cases] == [1, 1, 1]


def test_parts_in_unison_keep_their_own_lengths(tmp_path):
    from brasscribe_eval.quant_bench import evaluate

    # Two parts start the same pitch together; one holds it a beat, the other two.
    ref = [{"pitch": 60, "onset": 0.0, "offset": 0.5, "quarter": 0.0, "dur_quarter": 1.0, "part": "A"},
           {"pitch": 60, "onset": 0.0, "offset": 1.0, "quarter": 0.0, "dur_quarter": 2.0, "part": "B"},
           {"pitch": 62, "onset": 1.0, "offset": 1.5, "quarter": 2.0, "dur_quarter": 1.0, "part": "A"}]
    (tmp_path / "reference.json").write_text(json.dumps(ref))
    r = evaluate(tmp_path, None, beats_override=np.arange(0.0, 4.0, 0.5))
    assert r["duration_acc"] == 1.0


def _rebaseline(stored: dict, measured: dict, **result) -> tuple[dict, list[dict]]:
    baselines = {"tolerance": 0.01, "suites": {"s": {"source": "doc", "metrics": stored}}}
    new, changes = suites.rebaseline([{"suite": "s", "status": "ran", "metrics": measured, **result}], baselines)
    return new["suites"]["s"]["metrics"], changes


def test_a_value_on_a_rounding_half_rounds_the_same_way_from_either_side():
    below, above = np.nextafter(0.8125, 0), np.nextafter(0.8125, 1)  # what two sums of the same clips can give
    assert suites.stable_round(below) == suites.stable_round(0.8125) == suites.stable_round(above) == 0.812
    assert suites.stable_round(np.nextafter(0.4375, 0)) == suites.stable_round(np.nextafter(0.4375, 1)) == 0.438
    assert suites.stable_round(0.1 + 0.2) == 0.3 and suites.stable_round(2 / 3) == 0.667
    assert suites.stable_round(0.81251) == 0.813  # really past the half


def test_regenerating_baselines_leaves_a_value_on_a_rounding_half_as_it_is_stored():
    for stored in (0.812, 0.813):  # either rounding of 0.8125 was written once
        for measured in (np.nextafter(0.8125, 0), 0.8125, np.nextafter(0.8125, 1)):
            metrics, changes = _rebaseline({"m": stored, "e": {"value": stored, "higher_is_better": False}},
                                           {"m": measured, "e": measured})
            assert (metrics["m"], metrics["e"]["value"], changes) == (stored, stored, [])


def test_regenerating_baselines_changes_only_the_metrics_that_moved():
    stored = {"same": 0.6, "moved": 0.6, "error": {"value": 0.108, "higher_is_better": False, "tolerance": 0.02},
              "nan": 0.5, "absent": 0.5, "part.f1": 0.5, "coarse": 53.2}
    measured = {"same": 0.6004, "moved": 0.6006, "error": 0.2, "nan": math.nan, "part.f1": 0.9, "coarse": 53.2,
                "not_gated": 0.1}
    metrics, changes = _rebaseline(stored, measured, skipped_parts=["part"])
    assert metrics == {"same": 0.6, "moved": 0.601, "error": {"value": 0.2, "higher_is_better": False, "tolerance": 0.02},
                       "nan": 0.5, "absent": 0.5, "part.f1": 0.5, "coarse": 53.2}
    assert changes == [{"suite": "s", "metric": "moved", "old": 0.6, "new": 0.601},
                       {"suite": "s", "metric": "error", "old": 0.108, "new": 0.2}]
    assert list(metrics) == list(stored)  # the file keeps its order

    untouched = {"tolerance": 0.01, "suites": {"s": {"metrics": {"m": 0.5}}, "other": {"metrics": {"m": 0.5}}}}
    for status in ("skipped", "error"):
        new, changes = suites.rebaseline([{"suite": "s", "status": status, "metrics": {"m": 0.9}}], untouched)
        assert (new, changes) == (untouched, [])


def test_the_baselines_file_is_written_as_it_is_kept(tmp_path):
    kept = suites.BASELINES.read_text()
    suites.write_baselines(json.loads(kept), tmp_path / "baselines.json")
    assert (tmp_path / "baselines.json").read_text() == kept  # so a regeneration's diff is the changed values only
