"""The band's own soloist: faithful placement as played inside the solo range, and its range check.

Twin of core/targets/brass/tests/soloist.rs, plus arrangement-level checks on the Mikkel composition.
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from brasscribe_music.arranger import _layer, _place_line, arrange_layers, in_register, place_soloist
from brasscribe_music.instruments import (BRASS_BAND, INSTRUMENTS, MINIMAL_BAND, QUARTET, lead_lineup, seat_lineup,
                                          validate_part)
from brasscribe_music.score_model import Composition, Note

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "mikkel-arranged-band" / "composition.json"
CORNET = INSTRUMENTS["bb-cornet"]


def line(pitches):
    return [Note(p, 12 * i, 12) for i, p in enumerate(pitches)]


def test_the_cornet_soloist_reaches_written_d6():
    assert CORNET.solo_range == (52, 84)
    assert CORNET.pro == (52, 82)
    assert CORNET.placement_limit == (52, 82)  # section cornets keep the playable top


def test_a_phrase_inside_the_range_is_written_as_played():
    w = []
    solo = line([69, 72, 76, 81, 83, 84, 81, 79, 74])
    assert [n.pitch for n in place_soloist(solo, BRASS_BAND.lead_part, w)] == [n.pitch for n in solo]
    assert w == []


def test_one_outlier_moves_alone_and_the_run_keeps_its_direction():
    w = []
    placed = [n.pitch for n in place_soloist(line([72, 74, 76, 90, 79, 81]), BRASS_BAND.lead_part, w)]
    assert placed == [72, 74, 76, 78, 79, 81]
    assert all(b > a for a, b in zip(placed, placed[1:]))
    assert w == ["Solo Cornet: moved 90 to 78 at tick 36 (outside the range)"]


def test_a_phrase_mostly_outside_takes_the_fewest_octaves():
    w = []
    assert [n.pitch for n in place_soloist(line([40, 43, 47, 50, 52]), BRASS_BAND.lead_part, w)] == [52, 55, 59, 62, 64]
    assert w == []


def test_the_register_gate_needs_95_percent_inside():
    ps = [60] * 19 + [40]
    assert in_register(line(ps), CORNET.solo_range)
    assert not in_register(line(ps + [41]), CORNET.solo_range)
    assert not in_register([], CORNET.solo_range)


def test_the_soloist_lead_is_checked_against_the_solo_range():
    for lineup in (BRASS_BAND, MINIMAL_BAND):
        assert lineup.soloist_lead
        assert lineup.check("Solo Cornet", 84) == "uncomfortable"
        assert lineup.check("Solo Cornet", 85) == "impossible"
        assert lineup.check("Solo Cornet", 79) == "ok"
        assert lineup.check("2nd Cornet", 83) == "impossible"  # section cornets keep 82
    assert BRASS_BAND.check("Repiano Cornet", 83) == "impossible"
    assert [(i.index, i.level) for i in validate_part(BRASS_BAND, "Solo Cornet", [60, 84, 85])] == \
        [(1, "uncomfortable"), (2, "impossible")]


def test_not_a_soloist_lead_quartet_solo_take_or_moved_tune():
    assert not QUARTET.soloist_lead
    assert QUARTET.check("1st Cornet", 83) == "impossible"
    assert not seat_lineup("solo-cornet").soloist_lead
    euph = lead_lineup(BRASS_BAND, "euphonium")
    assert euph.lead_moved and not euph.soloist_lead
    assert euph.check("Solo Cornet", 83) == "impossible"
    own = lead_lineup(BRASS_BAND, "solo-cornet")
    assert not own.lead_moved and own.soloist_lead


@pytest.fixture(scope="module")
def mikkel():
    if not GOLDEN.exists():
        if os.environ.get("BRASSCRIBE_REQUIRE_DATA"):
            pytest.fail(f"missing {GOLDEN}")
        pytest.skip("data/golden not available")
    return Composition.from_json(GOLDEN)


def test_mikkel_faithful_lead_is_written_as_played(mikkel):
    arr = arrange_layers(mikkel)
    solo = sorted(_layer(mikkel, "solo"), key=lambda n: n.start)
    lead = sorted(arr.parts["Solo Cornet"], key=lambda n: n.start)
    assert [(n.start, n.pitch) for n in lead] == [(n.start, n.pitch) for n in solo]
    assert max(n.pitch for n in lead) == 84
    assert not [w for w in arr.warnings if w.startswith("Solo Cornet:")]
    for part in arr.lineup.parts:
        if part.name != "Percussion":
            assert not [i for i in validate_part(arr.lineup, part.name, [n.pitch for n in arr.parts[part.name]])
                        if i.level == "impossible"], part.name


def test_a_line_outside_the_register_keeps_todays_placement(mikkel):
    # The solo two octaves down (a euphonium's register): the gate fails, and the lead is placed as before.
    low = replace(mikkel, voices=[replace(v, notes=[replace(n, pitch=n.pitch - 24) for n in v.notes]) if v.layer == "solo" else v
                                  for v in mikkel.voices])
    arr = arrange_layers(low)
    assert arr.parts["Solo Cornet"] == _place_line(_layer(low, "solo"), BRASS_BAND.lead_part, [])


def test_the_soloist_rule_is_faithful_only(mikkel):
    for mode in ("standard", "easier"):
        arr = arrange_layers(mikkel, difficulty=mode)
        assert max(n.pitch for n in arr.parts["Solo Cornet"]) <= 79, mode


def test_the_tune_on_a_band_part_keeps_todays_placement(mikkel):
    lineup = lead_lineup(BRASS_BAND, "flugelhorn")
    arr = arrange_layers(mikkel, lineup)
    assert arr.parts["Flugelhorn"] == _place_line(_layer(mikkel, "solo"), lineup.lead_part, [])


def test_a_low_take_in_the_cornets_range_is_written_as_played():
    # A take with no seat in a horn's register (E3-G4) passes the gate: the small band's Solo Cornet keeps
    # the octave played, low on the staff, rather than lifting it into the reading range.
    solo = line([52, 55, 57, 60, 62, 64, 67, 65, 62, 60])
    assert in_register(solo, CORNET.solo_range)
    assert [n.pitch for n in place_soloist(solo, MINIMAL_BAND.lead_part, [])] == [n.pitch for n in solo]
    assert [n.pitch for n in _place_line(solo, MINIMAL_BAND.lead_part, [])] != [n.pitch for n in solo]


def test_a_lead_a_semitone_past_the_range_moves_only_around_its_peaks(mikkel):
    # Mikkel a semitone up: 5 notes above the cornet's solo range of 84. Only the passages around them
    # change octave, split at their leaps inside the solo range, never by two octaves.
    up = replace(mikkel, voices=[replace(v, notes=[replace(n, pitch=n.pitch + 1) for n in v.notes]) if v.layer == "solo" else v
                                 for v in mikkel.voices])
    solo = {n.start: n.pitch for n in _layer(up, "solo")}
    lead = arrange_layers(up).parts["Solo Cornet"]
    moved = [n for n in lead if n.pitch != solo[n.start]]
    assert all(abs(n.pitch - solo[n.start]) == 12 for n in moved)
    assert all(52 <= n.pitch <= 84 for n in lead)
    assert len(moved) < 60, len(moved)
