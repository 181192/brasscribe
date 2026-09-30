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
