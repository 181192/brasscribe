"""Range invariants on the Mikkel golden composition, for every lineup and difficulty mode.

No part sounds a note the lineup's range check calls impossible (Lineup.check: the soloist lead
against its instrument's solo range, every other part against MuseScore's professional range). Only
the band's soloist lead in faithful mode may pass its instrument's pro range, and the easier modes
keep the lead inside the range the mode promises. Together they guard the section cornets' top of
82 against any wider soloist range.
"""

from pathlib import Path

import pytest

from brasscribe_music.arranger import arrange_layers
from brasscribe_music.difficulty import MODES, mode_range
from brasscribe_music.instruments import LINEUPS
from brasscribe_music.score_model import Composition

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "mikkel-arranged-band" / "composition.json"


@pytest.fixture(scope="module")
def golden() -> Composition:
    if not GOLDEN.exists():
        pytest.skip(f"missing {GOLDEN}")
    return Composition.from_json(GOLDEN)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("lineup", sorted(LINEUPS))
def test_no_part_sounds_outside_its_range(golden, lineup, mode):
    lu = LINEUPS[lineup]
    arr = arrange_layers(golden, lu, difficulty=mode)
    for part in lu.parts:
        if part.instrument.clef == "percussion":
            continue
        notes = arr.parts.get(part.name, [])
        bad = sorted({n.pitch for n in notes if lu.check(part.name, n.pitch) == "impossible"})
        assert not bad, f"{lineup}/{mode}: {part.name} ({part.instrument.name}) sounds {bad}, impossible"
        if part.name == lu.lead and lu.soloist_lead and mode == "faithful":
            continue
        lo, hi = part.instrument.pro
        bad = sorted({n.pitch for n in notes if not lo <= n.pitch <= hi})
        assert not bad, f"{lineup}/{mode}: {part.name} ({part.instrument.name}) sounds {bad} outside {lo}-{hi}"


@pytest.mark.parametrize("mode", ["standard", "easier"])
@pytest.mark.parametrize("lineup", sorted(LINEUPS))
def test_lead_stays_inside_the_modes_range(golden, lineup, mode):
    lu = LINEUPS[lineup]
    lead = lu.lead_part
    lo, hi = mode_range(lead, mode)
    notes = arrange_layers(golden, lu, difficulty=mode).parts[lead.name]
    bad = sorted({n.pitch for n in notes if not lo <= n.pitch <= hi})
    assert not bad, f"{lineup}/{mode}: {lead.name} sounds {bad} outside the mode's range {lo}-{hi}"
