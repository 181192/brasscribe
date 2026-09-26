from brasscribe_music.arranger import _climax_spans, _figurate, arrange_layers
from brasscribe_music.difficulty import apply_difficulty, easy_range
from brasscribe_music.instruments import BRASS_BAND, MINIMAL_BAND
from brasscribe_music.keys import semitones_to
from brasscribe_music.score_model import Composition, Dynamic, KeySig, Meter, Note, Voice, VoiceRole


def _comp():
    # Solo: 16th pairs on each 8th (chord tone, then passing tone); strings: C major pad, attacked on every beat.
    solo = []
    for i in range(16):
        solo += [Note(72, i * 12, 6), Note(74, i * 12 + 6, 6)]
    strings = [Note(p, b * 24, 24) for b in range(8) for p in (60, 64, 67)]
    bass = [Note(36, b * 96, 96) for b in range(2)]
    return Composition("d", [Voice("solo", VoiceRole.MELODY, solo, layer="solo"),
                             Voice("strings", VoiceRole.HARMONY, strings, layer="strings"),
                             Voice("bass", VoiceRole.BASS, bass, layer="bass")], [Meter(0, 4)], [KeySig(0, 0)],
                       dynamics=[Dynamic(96, "solo", "ff"), Dynamic(96, "strings", "f")])


def sixteenths(notes):
    return sum(n.dur < 12 for n in notes)


def test_faithful_is_unchanged_and_modes_simplify():
    comp = _comp()
    f = arrange_layers(comp)
    s = arrange_layers(comp, difficulty="standard")
    e = arrange_layers(comp, difficulty="easier")
    assert sixteenths(f.parts["Solo Cornet"]) == 32
    # Standard merges pairs whose dropped note (D) is not a chord tone; easier merges all.
    assert sixteenths(s.parts["Solo Cornet"]) == 0 and sixteenths(e.parts["Solo Cornet"]) == 0
    assert {n.pitch % 12 for n in s.parts["Solo Cornet"]} == {0}  # the chord tone C is kept
    assert apply_difficulty(f.parts, f.lineup, "faithful") is f.parts


def test_easier_keeps_parts_in_easy_range_and_eighths():
    e = arrange_layers(_comp(), difficulty="easier")
    for part in e.lineup.parts:
        lo, hi = easy_range(part)
        for n in e.parts[part.name]:
            if part.instrument.clef != "percussion":
                assert lo <= n.pitch <= hi, part.name
                if part.name != "Solo Cornet":
                    assert n.start % 12 == 0 and n.dur >= 12 or n.dur < 12 and n.end % 12 == 0, part.name


def test_soprano_doubles_at_climax_only_outside_faithful():
    comp = _comp()
    assert not arrange_layers(comp).parts["Soprano Cornet"]
    sop = arrange_layers(comp, difficulty="standard").parts["Soprano Cornet"]
    assert sop and all(n.start >= 96 for n in sop)
    assert _climax_spans(comp) == [(96, comp.end_tick)]


def test_figuration_follows_source_attacks():
    slots = [(0, 96, [0, 4, 7])]
    assert _figurate(slots, [0, 24, 48, 72, 30]) == [(0, 24, [0, 4, 7]), (24, 48, [0, 4, 7]), (48, 72, [0, 4, 7]),
                                                     (72, 96, [0, 4, 7])]
    comp = _comp()
    pads = arrange_layers(comp, difficulty="standard").parts["Solo Horn"]
    assert {n.start for n in pads} >= {0, 24, 48, 72}


def test_minimal_lineup_through_the_layered_path():
    arr = arrange_layers(_comp(), MINIMAL_BAND)
    assert set(arr.parts) == {p.name for p in MINIMAL_BAND.parts}
    assert arr.parts["Solo Cornet"] and arr.parts["E♭ Bass"] and arr.parts["Solo Horn"]


def test_semitones_to_target_key():
    assert semitones_to(KeySig(0, 0), "Bb") == -2
    assert semitones_to(KeySig(0, 0), "-2") == -2
    assert semitones_to(KeySig(0, 0, "lydian"), "Bb") == 5  # F lydian -> Bb lydian
    assert semitones_to(KeySig(0, 0, "minor"), "Am") == 0
    assert semitones_to(KeySig(0, 0), "F#") == 6
    assert BRASS_BAND.by_name("Soprano Cornet")
