from music21 import converter

from brasscribe_music.arranger import arrange
from brasscribe_music.musicxml import build_band_score, write_musicxml
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
    out = write_musicxml(score, tmp_path / "band.musicxml")
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
            assert part.instrument.check(n.pitch) != "impossible", (part.name, n.pitch)
