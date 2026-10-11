"""The trumpet seat: a trumpet player takes the lead part (written for trumpet) in the bands.

Twin of core/target-brass/tests/seats.rs::the_trumpet_takes_the_lead, plus arrangements of Mikkel.
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from brasscribe_music.arranger import arrange_layers, composition_lineup
from brasscribe_music.instruments import (INSTRUMENTS, LINEUPS, SeatPart, lead_lineup, part_banks, seat_by_id, seat_lineup,
                                          seat_part, with_seat)
from brasscribe_music.score_model import Composition

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "mikkel-arranged-band" / "composition.json"


def test_the_trumpet_is_musescores_bb_trumpet():
    t = INSTRUMENTS["bb-trumpet"]
    assert (t.name, t.chromatic, t.diatonic, t.clef, t.pro, t.comfortable) == ("Trumpet in B♭", -2, -1, "treble", (52, 85), (52, 80))
    assert (t.gm_program, t.sound, t.solo_range) == (56, "brass.trumpet.bflat", (52, 85))
    assert (t.preferred, t.placement_limit) == (INSTRUMENTS["bb-cornet"].preferred, INSTRUMENTS["bb-cornet"].placement_limit)


@pytest.mark.parametrize("key", ["band", "minimal"])
def test_the_trumpet_takes_the_lead(key):
    assert seat_part(key, "trumpet") == SeatPart("Trumpet", False, True, takes="Solo Cornet")
    base = LINEUPS[key]
    lu = with_seat(base, key, "trumpet")
    assert lu.lead == "Trumpet" and not lu.has("Solo Cornet") and lu.soloist_lead and not lu.lead_moved
    assert [p.name for p in lu.parts] == [("Trumpet" if p.name == "Solo Cornet" else p.name) for p in base.parts]
    assert lu.by_name("Trumpet").players == base.by_name("Solo Cornet").players
    assert lead_lineup(base, "trumpet") == lu


def test_the_quartet_gives_a_trumpet_the_1st_cornet():
    assert seat_part("quartet", "trumpet") == SeatPart("1st Cornet", False, True)
    assert with_seat(LINEUPS["quartet"], "quartet", "trumpet") is LINEUPS["quartet"]


def test_seat_facts():
    s = seat_by_id("trumpet")
    assert s.tune and s.reads == ("treble",) and s.own_part.instrument.id == "bb-trumpet"
    assert part_banks()["Trumpet"] == 8
    take = seat_lineup("trumpet")
    assert take.lead == "Trumpet" and take.lead_part.instrument.pro == (52, 85)
    assert seat_part("minimal", "soprano-cornet").takes is None  # a band seat never takes the lead


@pytest.fixture(scope="module")
def mikkel():
    if not GOLDEN.exists():
        if os.environ.get("BRASSCRIBE_REQUIRE_DATA"):
            pytest.fail(f"missing {GOLDEN}")
        pytest.skip("data/golden not available")
    return Composition.from_json(GOLDEN)


@pytest.mark.parametrize("mode", ["faithful", "standard", "easier"])
def test_a_trumpet_players_band_has_the_same_notes(mikkel, mode):
    with_tpt = replace(mikkel, arrangement={"lineup": "band", "difficulty": mode, "transpose_semitones": 0, "seat": "trumpet"})
    lu, _ = composition_lineup(with_tpt)
    assert lu.lead == "Trumpet"
    a = arrange_layers(with_tpt, lu, difficulty=mode)
    b = arrange_layers(mikkel, difficulty=mode)
    assert a.parts["Trumpet"] == b.parts["Solo Cornet"]
    assert {k: v for k, v in a.parts.items() if k != "Trumpet"} == {k: v for k, v in b.parts.items() if k != "Solo Cornet"}
    assert all(a.lineup.check("Trumpet", n.pitch) != "impossible" for n in a.parts["Trumpet"])
