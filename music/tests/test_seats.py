"""Seats, the seat -> part table, and where each part comes from (part_sources)."""

import json
from pathlib import Path

import pytest

from brasscribe_music.arranger import ARRANGED, RECORDING, YOUR_RECORDING, part_sources
from brasscribe_music.instruments import (BRASS_BAND, LINEUPS, SEAT_IDS, SEAT_PARTS, SEATS, check_reads, lead_lineup,
                                          part_banks, seat_by_id, seat_part)
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "golden" / "mikkel-arranged-band" / "composition.json"

# The seat -> part table as the plan writes it: (full band, small band, quartet); None = no part.
TABLE = {
    "soprano-cornet": ("Soprano Cornet", "Solo Cornet", "1st Cornet"),
    "solo-cornet": ("Solo Cornet", "Solo Cornet", "1st Cornet"),
    "repiano-cornet": ("Repiano Cornet", "2nd Cornet", "2nd Cornet"),
    "2nd-cornet": ("2nd Cornet", "2nd Cornet", "2nd Cornet"),
    "3rd-cornet": ("3rd Cornet", "2nd Cornet", "2nd Cornet"),
    "flugelhorn": ("Flugelhorn", "Flugelhorn", "2nd Cornet"),
    "solo-horn": ("Solo Horn", "Solo Horn", "Tenor Horn"),
    "1st-horn": ("1st Horn", "Solo Horn", "Tenor Horn"),
    "2nd-horn": ("2nd Horn", "Solo Horn", "Tenor Horn"),
    "1st-baritone": ("1st Baritone", "Euphonium", "Euphonium"),
    "2nd-baritone": ("2nd Baritone", "Euphonium", "Euphonium"),
    "1st-trombone": ("1st Trombone", "1st Trombone", "Euphonium"),
    "2nd-trombone": ("2nd Trombone", "1st Trombone", "Euphonium"),
    "bass-trombone": ("Bass Trombone", "E♭ Bass", "Euphonium"),
    "euphonium": ("Euphonium", "Euphonium", "Euphonium"),
    "eb-bass": ("E♭ Bass", "E♭ Bass", "Euphonium"),
    "bb-bass": ("B♭ Bass", "B♭ Bass", "Euphonium"),
    "percussion": ("Percussion", None, None),
}
# (seat, lineup) pairs the plan marks as a different key.
# As the player reads by default: the bass trombone reads bass clef at concert pitch, and so do its mapped parts.
OTHER_KEY = {("soprano-cornet", "minimal"), ("soprano-cornet", "quartet"), ("eb-bass", "quartet")}


def test_seats_are_the_contest_band():
    assert [s.part for s in SEATS] == [p.name for p in BRASS_BAND.parts]
    assert len(set(SEAT_IDS)) == 18 and all(i.isascii() and " " not in i for i in SEAT_IDS)


@pytest.mark.parametrize("seat", list(TABLE))
def test_seat_part_table(seat):
    assert SEAT_PARTS[seat] == TABLE[seat]
    for lineup, want in zip(("band", "minimal", "quartet"), TABLE[seat]):
        sp = seat_part(lineup, seat)
        assert sp.part == want
        if want is None:
            assert not sp.exact and not sp.same_key
            continue
        assert LINEUPS[lineup].has(want)
        assert sp.exact == (want == seat_by_id(seat).part)
        assert sp.same_key == ((seat, lineup) not in OTHER_KEY)
    assert seat_part("full", seat) == seat_part("band", seat)
    assert seat_part(None, seat) == seat_part("band", seat)


def test_every_resolved_part_has_a_sound_and_a_bank():
    mapping = json.loads((ROOT / "sounds" / "mapping.json").read_text())
    banks = part_banks()
    for row in TABLE.values():
        for name in row:
            if name is None:
                continue
            assert name in mapping["parts"]
            assert name == "Percussion" or name in banks


# Seats whose part can carry the tune (Role MELODY/SOLO, not the bass line); the Rust core's list too.
TUNE = ["soprano-cornet", "solo-cornet", "repiano-cornet", "2nd-cornet", "3rd-cornet", "flugelhorn", "solo-horn", "1st-horn",
        "2nd-horn", "1st-trombone", "2nd-trombone", "euphonium"]


def test_tune_follows_the_roles():
    assert [s.id for s in SEATS if s.tune] == TUNE
    for s in SEATS:
        try:
            lead_lineup(BRASS_BAND, s.id)
            leads = True
        except ValueError:
            leads = False
        assert s.tune == leads, s.id


@pytest.mark.parametrize("seat", list(TABLE))
@pytest.mark.parametrize("lineup", ["band", "minimal", "quartet"])
def test_default_reading_in_every_lineup(seat, lineup):
    """With no `reads`, the seat's part is written in the seat's own first clef, and a bass-clef part at
    concert pitch: the bass trombonist gets E♭ Bass and Euphonium in bass clef."""
    from brasscribe_music.instruments import with_reading

    s, part = seat_by_id(seat), seat_part(lineup, seat).part
    if part is None or s.default_reading is None:  # percussion: no part, or no clef to read
        return
    inst = with_reading(LINEUPS[lineup], seat, part, None).by_name(part).instrument
    if s.default_reading == "bass":
        assert (inst.clef, inst.chromatic) == ("bass", 0)
    else:
        assert inst.clef == s.default_reading == "treble"
    if "bass" in s.reads:  # an explicit reading still wins
        inst = with_reading(LINEUPS[lineup], seat, part, "bass").by_name(part).instrument
        assert (inst.clef, inst.chromatic) == ("bass", 0)


def test_bass_trombone_reads_bass_clef_in_the_small_band_and_quartet():
    from brasscribe_music.arranger import composition_lineup

    for lineup, part in (("minimal", "E♭ Bass"), ("quartet", "Euphonium")):
        c = Composition("t", [Voice("melody", VoiceRole.MELODY, [Note(60, 0, 24)])], [Meter(0, 4)], [KeySig(0, 0)])
        c.arrangement = {"lineup": lineup, "difficulty": "faithful", "transpose_semitones": 0, "seat": "bass-trombone"}
        lu, _ = composition_lineup(c)
        inst = lu.by_name(part).instrument
        assert (inst.clef, inst.chromatic) == ("bass", 0), lineup
        assert [p for p in lu.parts if p.name != part] == [p for p in LINEUPS[lineup].parts if p.name != part]


def test_seat_errors():
    with pytest.raises(ValueError):
        seat_part("band", "tuba")
    with pytest.raises(ValueError):
        seat_part("orchestra", "euphonium")


def test_reads():
    check_reads("euphonium", "bass")
    check_reads("euphonium", "treble")
    check_reads("bass-trombone", "bass")
    check_reads(None, None)
    for seat, reads in (("solo-cornet", "bass"), ("bass-trombone", "treble"), (None, "bass"), ("euphonium", "alto"),
                        ("percussion", "treble")):
        with pytest.raises(ValueError):
            check_reads(seat, reads)
    assert seat_by_id("eb-bass").reads == ("treble", "bass")


def _comp(layers: dict[str, bool], arrangement: dict | None = None) -> Composition:
    roles = {"solo": VoiceRole.MELODY, "bass": VoiceRole.BASS, "strings": VoiceRole.HARMONY,
             "brass": VoiceRole.HARMONY, "drums": VoiceRole.RHYTHM}
    voices = [Voice(k, roles[k], [Note(60, 0, 24)] if on else [], None, k) for k, on in layers.items()]
    c = Composition("t", voices, [Meter(0, 4)], [KeySig(0, 0)])
    c.arrangement = arrangement
    return c


@pytest.mark.skipif(not GOLDEN.exists(), reason="no Mikkel golden output")
def test_part_sources_mikkel():
    src = part_sources(Composition.from_json(GOLDEN))
    heard = {"Solo Cornet", "E♭ Bass", "B♭ Bass", "Euphonium", "Bass Trombone", "Percussion"}
    assert list(src) == [p.name for p in BRASS_BAND.parts]
    assert {k for k, v in src.items() if v == RECORDING} == heard
    assert all(v == ARRANGED for k, v in src.items() if k not in heard)


def test_part_sources_band_job():
    # Non-layered (brass-band, pop-rock): the tune and the basses are heard, the rest arranged.
    c = Composition("t", [Voice("melody", VoiceRole.MELODY, [Note(60, 0, 24)]), Voice("bass", VoiceRole.BASS, [Note(40, 0, 24)]),
                          Voice("harmony", VoiceRole.HARMONY, [Note(64, 0, 24)])], [Meter(0, 4)], [KeySig(0, 0)])
    src = part_sources(c)
    assert {k for k, v in src.items() if v == RECORDING} == {"Solo Cornet", "E♭ Bass", "B♭ Bass"}
    c.arrangement = {"lineup": "quartet", "difficulty": "faithful", "transpose_semitones": 0}
    assert part_sources(c) == {"1st Cornet": RECORDING, "2nd Cornet": ARRANGED, "Tenor Horn": ARRANGED,
                               "Euphonium": RECORDING}


def test_part_sources_layers():
    full = {"solo": True, "bass": True, "strings": True, "brass": True, "drums": True}
    quartet = part_sources(_comp(full, {"lineup": "quartet", "difficulty": "faithful", "transpose_semitones": 0}))
    assert quartet == {"1st Cornet": RECORDING, "2nd Cornet": ARRANGED, "Tenor Horn": ARRANGED, "Euphonium": RECORDING}
    no_strings = part_sources(_comp({**full, "strings": False, "drums": False}))
    assert no_strings["Euphonium"] == ARRANGED and no_strings["Percussion"] == ARRANGED
    assert no_strings["Solo Cornet"] == RECORDING


def test_part_sources_solo_take():
    # A solo take (only the solo layer has notes) without a seat: today's minimal band, the tune is yours.
    src = part_sources(_comp({"solo": True, "bass": False, "strings": False, "brass": False, "drums": False},
                             {"lineup": "minimal", "difficulty": "faithful", "transpose_semitones": 0}))
    assert src["Solo Cornet"] == YOUR_RECORDING
    assert all(v == ARRANGED for k, v in src.items() if k != "Solo Cornet")


def test_lead_lineup():
    from brasscribe_music.instruments import MINIMAL_BAND, QUARTET, lead_lineup

    assert lead_lineup(BRASS_BAND, "euphonium").lead == "Euphonium"
    assert lead_lineup(BRASS_BAND, "solo-cornet") is BRASS_BAND
    assert lead_lineup(MINIMAL_BAND, "1st-baritone").lead == "Euphonium"  # the small band's part for it
    for lineup, seat in ((QUARTET, "euphonium"), (BRASS_BAND, "1st-baritone"), (BRASS_BAND, "eb-bass"),
                         (MINIMAL_BAND, "percussion"), (BRASS_BAND, "bass-trombone")):
        with pytest.raises(ValueError):
            lead_lineup(lineup, seat)


@pytest.mark.skipif(not GOLDEN.exists(), reason="no Mikkel golden output")
def test_euphonium_solo_with_band():
    from brasscribe_music.arranger import arrange_composition, layer_of_part

    comp = Composition.from_json(GOLDEN)
    plain = arrange_composition(comp)
    comp.arrangement = {"lineup": "band", "difficulty": "faithful", "transpose_semitones": 0, "seat": "euphonium",
                        "lead": "seat"}
    arr = arrange_composition(comp)
    assert arr.lineup.lead == "Euphonium"
    solo = [n for v in comp.voices if v.layer == "solo" for n in v.notes]
    assert [n.start for n in arr.parts["Euphonium"]] == [n.start for n in plain.parts["Solo Cornet"]]
    assert {n.pitch % 12 for n in arr.parts["Euphonium"]} <= {n.pitch % 12 for n in solo}
    assert arr.parts["Solo Horn"] and arr.parts["Solo Cornet"] and not arr.parts["Soprano Cornet"]
    assert layer_of_part(arr.lineup, "Euphonium") == "solo" and layer_of_part(arr.lineup, "Solo Cornet") == "strings"
    src = part_sources(comp)
    assert src["Euphonium"] == RECORDING and src["Solo Horn"] == RECORDING and src["Solo Cornet"] == ARRANGED
    # Without lead=seat the seat changes no notes of a band take.
    comp.arrangement = {"lineup": "band", "difficulty": "faithful", "transpose_semitones": 0, "seat": "euphonium"}
    assert arrange_composition(comp).parts == plain.parts
