import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import musicxml_readability as r  # noqa: E402

FIXTURE = HERE / "fixtures" / "small.musicxml"


def metrics():
    parts, score = r.parse(FIXTURE)
    return {p.name: r.analyse_part(p, None) for p in parts}, parts, score


def test_ledger_lines():
    assert r.ledger_lines("E", 4, ("G", 2)) == 0
    assert r.ledger_lines("C", 4, ("G", 2)) == 1
    assert r.ledger_lines("A", 3, ("G", 2)) == 2
    assert r.ledger_lines("F", 3, ("G", 2)) == 3
    assert r.ledger_lines("A", 5, ("G", 2)) == 1
    assert r.ledger_lines("C", 6, ("G", 2)) == 2
    assert r.ledger_lines("C", 4, ("F", 4)) == 1
    assert r.ledger_lines("C", 2, ("F", 4)) == 2


def test_solo_cornet_metrics():
    m, _, _ = metrics()
    solo, flags = m["Solo Cornet"]
    assert solo["notes"] == 7
    assert solo["short_lt16_pct"] == round(100 / 7, 1)
    assert solo["sixteenth_pct"] == round(200 / 7, 1)
    assert solo["tie_stub_pct"] == round(100 / 7, 1)
    assert solo["double_dotted"] == 1
    assert solo["colour_only_uncertain"] == 1
    assert solo["uncertain_pct"] == round(200 / 7, 1)
    assert solo["awkward_spelling"] == 2  # E#5 twice
    assert solo["out_of_extreme"] == 1   # E3
    assert solo["max_ledger"] == 3
    assert solo["empty_bars"] == 1
    assert "shorter than 16th" in flags["1"]
    assert "double-dotted value" in flags["3"]


def test_tacet_and_divisi_and_abbreviations():
    m, parts, _ = metrics()
    assert m["Repiano Cornet"][0]["tacet"] is True
    bt = m["Bass Trombone"][0]
    assert bt["divisi_notes"] == 1
    assert bt["max_ledger"] == 2
    agg = r.aggregate([x[0] for x in m.values()], parts, None)
    assert agg["tacet_parts"] == ["Repiano Cornet"]
    assert agg["duplicate_abbreviations"] == {"Cnt.": ["Solo Cornet", "Repiano Cornet"]}


def test_accidentals():
    m, _, _ = metrics()
    solo, _ = m["Solo Cornet"]
    assert solo["accidental_pct"] == round(100 / 7, 1)
    assert solo["bars_mixed_sharp_flat"] == 0


def test_range_filter_and_check_exit_code():
    parts, _ = r.parse(FIXTURE)
    solo = next(p for p in parts if p.name == "Solo Cornet")
    m, _ = r.analyse_part(solo, (3, 3))
    assert m["notes"] == 1
    assert r.main([str(FIXTURE), "--check"]) == 1
    assert r.main([str(FIXTURE)]) == 0
