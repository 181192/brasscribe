"""The brass quartet: 1st Cornet, 2nd Cornet, Tenor Horn, Euphonium, voiced as S A T B."""

import xml.etree.ElementTree as ET

import pytest

from brasscribe_music.arranger import (_perfect_parallels, arrange, arrange_composition, arrange_layers, chord_root,
                                       layer_of_part, voice_satb)
from brasscribe_music.difficulty import easy_range
from brasscribe_music.instruments import QUARTET, lineup_by_name, part_banks
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

NAMES = ["1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"]


def _cadence() -> Composition:
    """I-IV-V-I in C, one chord per bar: melody E F D C over C F G C."""
    mel = [Note(p, i * 96, 96) for i, p in enumerate([64, 65, 62, 60])]
    bass = [Note(p, i * 96, 96) for i, p in enumerate([48, 53, 43, 48])]
    chords = [(60, 64, 67), (60, 65, 69), (59, 62, 67), (60, 64, 67)]
    harm = [Note(p, i * 96, 96) for i, ch in enumerate(chords) for p in ch]
    return Composition("cadence", [Voice("m", VoiceRole.MELODY, mel), Voice("b", VoiceRole.BASS, bass),
                                   Voice("h", VoiceRole.HARMONY, harm)], [Meter(0, 4)], [KeySig(0, 0)])


def _at(notes, t):
    return next((n.pitch for n in notes if n.start <= t < n.end), None)


def test_quartet_lineup_roles_and_names():
    assert lineup_by_name("quartet") is QUARTET
    assert [p.name for p in QUARTET.parts] == NAMES
    assert (QUARTET.lead, QUARTET.bass, QUARTET.second_bass, QUARTET.satb) == ("1st Cornet", "Euphonium", None, True)
    assert [p.players for p in QUARTET.parts] == [1, 1, 1, 1]
    assert [p.midi_bank for p in QUARTET.parts] == [1, 4, 1, 3]
    banks = part_banks()
    assert banks["1st Cornet"] == 1 and banks["Tenor Horn"] == 1


def test_quartet_layers_follow_the_roles():
    assert [layer_of_part(QUARTET, n) for n in NAMES] == ["solo", "strings", "strings", "bass"]


def test_cadence_is_voiced_in_four_parts_without_faults():
    arr = arrange(_cadence(), QUARTET)
    assert set(arr.parts) == set(NAMES) and not arr.warnings
    assert [n.pitch for n in arr.parts["1st Cornet"]] == [64, 65, 62, 60]
    assert [n.pitch % 12 for n in arr.parts["Euphonium"]] == [0, 5, 7, 0]
    prev = None
    for t in (0, 96, 192, 288):
        s, a, tn, b = (_at(arr.parts[n], t) for n in NAMES)
        assert s > a >= tn > b, t
        assert s - a <= 12 and a - tn <= 12, t
        cur = [s, a, tn, b]
        if prev:
            assert _perfect_parallels(prev, cur) == 0, t
        prev = cur
    # Every chord complete (a fifth may be left out).
    for t, chord in zip((0, 96, 192, 288), ({0, 4}, {5, 9}, {7, 11}, {0, 4})):
        assert chord <= {_at(arr.parts[n], t) % 12 for n in NAMES}, t


def test_voice_satb_rules():
    # C major under E5, over C3: alto below the soprano, tenor above the bass, within an octave.
    a, t = voice_satb([0, 4, 7], 76, 48, None, (55, 79), (48, 70))
    assert 76 > a >= t > 48 and 76 - a <= 12 and a - t <= 12
    assert {a % 12, t % 12} | {76 % 12, 48 % 12} == {0, 4, 7}
    # No room between soprano and bass: no pair.
    assert voice_satb([0, 4, 7], 50, 48, None, (55, 79), (48, 70)) is None


def test_voice_satb_avoids_parallel_fifths():
    # C -> D major, soprano G -> F#, bass C -> D: an inner pair a fifth or octave apart over the
    # bass (the tenor on G and A would be) is refused.
    prev = [67, 64, 55, 48]
    assert _perfect_parallels(prev, [66, 62, 57, 50]) == 1  # tenor-bass G/C -> A/D
    a, t = voice_satb([2, 6, 9], 66, 50, prev, (55, 79), (48, 70))
    assert _perfect_parallels(prev, [66, a, t, 50]) == 0


def test_chord_root():
    assert chord_root([0, 4, 7], None) == 0
    assert chord_root([2, 5, 7, 11], 7) == 7  # G7
    assert chord_root([1, 4, 7], 4) == 4  # diminished: a third above, no perfect fifth -> the bass


def test_quartet_score_parts_transpositions_and_banks(tmp_path):
    comp = _cadence()
    arr = arrange(comp, QUARTET)
    out = write_musicxml(build_band_score(arr, comp), tmp_path / "q.musicxml", band_sounds(arr))
    raw = out.read_text()
    root = ET.fromstring(raw[raw.index("<score-partwise"):])
    sps = list(root.iter("score-part"))
    assert [sp.findtext("part-name") for sp in sps] == NAMES
    assert [sp.find("midi-instrument").findtext("midi-bank") for sp in sps] == ["1", "4", "1", "3"]
    tr = [(p.findtext(".//transpose/chromatic"), p.findtext(".//transpose/octave-change")) for p in root.findall("part")]
    assert tr == [("-2", None), ("-2", None), ("-9", None), ("-2", "-1")]


@pytest.mark.parametrize("mode", ["standard", "easier"])
def test_quartet_difficulty_keeps_inner_parts_in_range_and_uncrossed(mode):
    arr = arrange(_cadence(), QUARTET, mode)
    for p in QUARTET.parts:
        lo, hi = easy_range(p) if mode == "easier" else p.instrument.preferred
        assert all(lo <= n.pitch <= hi for n in arr.parts[p.name]), p.name
    for t in (0, 96, 192, 288):
        s, a, tn, b = (_at(arr.parts[n], t) for n in NAMES)
        assert s > a >= tn > b, t


def _layered() -> Composition:
    solo = [Note(p, i * 24, 24) for i, p in enumerate([72, 74, 76, 77, 79, 77, 76, 74] * 2)]
    strings = [Note(p, b * 96, 96) for b in range(4) for p in ((60, 64, 67) if b % 2 == 0 else (60, 65, 69))]
    bass = [Note(36 if b % 2 == 0 else 41, b * 96, 96) for b in range(4)]
    drums = [Note(36, i * 24, 12) for i in range(8)]
    return Composition("l", [Voice("solo", VoiceRole.MELODY, solo, layer="solo"),
                             Voice("strings", VoiceRole.HARMONY, strings, layer="strings"),
                             Voice("bass", VoiceRole.BASS, bass, layer="bass"),
                             Voice("drums", VoiceRole.RHYTHM, drums, layer="drums")], [Meter(0, 4)], [KeySig(0, 0)])


@pytest.mark.parametrize("mode", ["faithful", "standard", "easier"])
def test_layered_quartet(mode):
    comp = _layered()
    arr = arrange_layers(comp, QUARTET, difficulty=mode)
    assert set(arr.parts) == set(NAMES)
    assert any("drums left out" in w for w in arr.warnings)
    # The Euphonium plays the bass line (no countermelody over it).
    assert [n.pitch % 12 for n in arr.parts["Euphonium"]] == [0, 5, 0, 5]
    assert arr.parts["2nd Cornet"] and arr.parts["Tenor Horn"]
    for t in sorted({n.start for v in arr.parts.values() for n in v}):
        seq = [_at(arr.parts[n], t) for n in NAMES]
        assert all(x is None or y is None or y <= x for x, y in zip(seq, seq[1:])), (t, seq)


def test_arrange_composition_follows_the_recorded_lineup():
    comp = _cadence()
    comp.arrangement = {"lineup": "quartet", "difficulty": "faithful", "transpose_semitones": 0}
    assert set(arrange_composition(comp).parts) == set(NAMES)
    comp.arrangement = None
    assert "Solo Cornet" in arrange_composition(comp).parts
