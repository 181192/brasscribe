from music21 import converter

from brasscribe_music.arranger import arrange
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

F_MAJOR_TUNE = [65, 67, 69, 70, 72, 70, 69, 67, 65]  # F G A Bb C Bb A G F (concert)


def _comp() -> Composition:
    mel = [Note(p, i * 24, 24) for i, p in enumerate(F_MAJOR_TUNE)]
    bass = [Note(41, 0, 96), Note(36, 96, 96), Note(41, 192, 24)]
    harm = [Note(p, 0, 96) for p in (57, 60)] + [Note(p, 96, 96) for p in (55, 58)] + [Note(p, 192, 24) for p in (57, 60)]
    return Composition("test", [Voice("m", VoiceRole.MELODY, mel), Voice("b", VoiceRole.BASS, bass),
                                Voice("h", VoiceRole.HARMONY, harm)], [Meter(0, 4)], [KeySig(0, -1)])


def test_round_trip_sounding_pitch_and_written_keys(tmp_path):
    comp = _comp()
    arr = arrange(comp)
    score = build_band_score(arr, comp)
    out = write_musicxml(score, tmp_path / "band.musicxml", band_sounds(arr))
    back = converter.parse(out)

    names = [p.partName for p in back.parts]
    assert names[0] == "Solo Cornet"
    by_name = {p.partName: p for p in back.parts}

    # Written key signatures: concert F -> Bb parts in G (1 sharp), Eb parts in D (2 sharps).
    def fifths(part):
        return part.recurse().getElementsByClass("KeySignature").first().sharps
    assert fifths(by_name["Solo Cornet"]) == 1
    assert fifths(by_name["Solo Horn"]) == 2
    assert fifths(by_name["E♭ Bass"]) == 2

    # Sounding pitches survive the trip exactly once transposed.
    sounding = back.toSoundingPitch()
    for part in sounding.parts:
        got = [n.pitch.midi for n in part.recurse().notes if n.isNote]
        want = [n.pitch for n in sorted(arr.parts[part.partName], key=lambda n: n.start)]
        assert got == want, part.partName


def test_arranger_keeps_melody_and_bass_and_respects_ranges():
    comp = _comp()
    arr = arrange(comp)
    solo = [n.pitch % 12 for n in arr.parts["Solo Cornet"]]
    assert solo == [p % 12 for p in F_MAJOR_TUNE]
    assert [n.pitch % 12 for n in arr.parts["E♭ Bass"]] == [5, 0, 5]
    for part in arr.lineup.parts:
        for n in arr.parts[part.name]:
            assert arr.lineup.check(part.name, n.pitch) != "impossible", (part.name, n.pitch)


def test_instrument_sounds_are_written(tmp_path):
    comp = _comp()
    arr = arrange(comp)
    out = write_musicxml(build_band_score(arr, comp), tmp_path / "band.musicxml", band_sounds(arr))
    xml = out.read_text()
    assert "<instrument-sound>brass.tuba</instrument-sound>" in xml
    assert "<instrument-sound>brass.cornet</instrument-sound>" in xml


def test_composition_json_round_trip_keeps_numbers(tmp_path):
    import numpy as np
    comp = _comp()
    comp.voices[0].notes[0].start = np.int64(0)
    comp.first_downbeat = np.int64(3)
    comp.to_json(tmp_path / "c.json")
    back = Composition.from_json(tmp_path / "c.json")
    assert back.first_downbeat == 3 and isinstance(back.voices[0].notes[0].start, int)
    assert back.end_tick == comp.end_tick


def test_ties_are_numbered_so_readers_pair_them_without_guessing(tmp_path):
    """Every <tied> has a number: a start takes the lowest free one, its stop the open one on the same pitch. alphaTab
    1.8.4 mismatched unnumbered ties in transposing parts (notes sounding again, or held into the next phrase)."""
    from brasscribe_music.musicxml import _number_ties

    def note(step: str, *tied: str, alter: str = "") -> str:
        a = f"<alter>{alter}</alter>" if alter else ""
        return (f"<note><pitch><step>{step}</step>{a}<octave>5</octave></pitch><notations>"
                + "".join(f'<tied type="{t}" />' for t in tied) + "</notations></note>")

    p = tmp_path / "t.musicxml"
    p.write_text('<score-partwise><part id="P1"><measure>' + note("D", "start") + note("D", "stop", "start")
                 + note("D", "stop") + note("E", "start") + note("G", "start") + note("G", "stop")
                 + note("E", "stop", alter="0") + "</measure></part></score-partwise>", encoding="utf-8")
    _number_ties(p)
    import re
    got = [re.findall(r'<tied type="(\w+)" number="(\d)"', n) for n in re.findall(r"<note>.*?</note>", p.read_text())]
    assert got == [[("start", "1")], [("stop", "1"), ("start", "1")], [("stop", "1")], [("start", "1")], [("start", "2")],
                   [("stop", "2")], [("stop", "1")]]
