from brasscribe_music.arranger import arrange_layers
from brasscribe_music.keys import key_plan
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

C_MAJOR = [60, 62, 64, 65, 67, 69, 71, 72]
A_MAJOR = [69, 71, 73, 74, 76, 78, 80, 81]
F_LYDIAN = [65, 67, 69, 71, 72, 74, 76, 77]


def _bars(scale_pitches, first_bar, n_bars):
    return [Note(scale_pitches[i % 8], (first_bar * 4 + i) * 24, 24) for i in range(n_bars * 4)]


def test_modulation_gets_a_key_change_and_back():
    notes = _bars(C_MAJOR, 0, 8) + _bars(A_MAJOR, 8, 8) + _bars(C_MAJOR, 16, 8)
    plan = key_plan(notes, 96)
    assert [(k.tick // 96, k.fifths) for k in plan.keys] == [(0, 0), (8, 3), (16, 0)]


def test_chromatic_neighbours_do_not_modulate():
    notes = _bars(C_MAJOR, 0, 16)
    notes[20].pitch = 61  # one C# in bar 6
    notes[24].pitch = 66  # one F# in bar 7
    assert [k.fifths for k in key_plan(notes, 96).keys] == [0]


def test_mode_is_named_from_the_tonic():
    notes = [Note(p, i * 24, 48 if p in (65, 72) else 24) for i, p in enumerate(F_LYDIAN * 4)]
    notes += [Note(41, i * 96, 96) for i in range(8)]  # F pedal
    k, = key_plan(notes, 96).keys
    assert k.fifths == 0 and k.mode == "lydian"


def test_key_changes_and_very_uncertain_marks_are_written(tmp_path):
    solo = _bars(C_MAJOR, 0, 4) + _bars(A_MAJOR, 4, 4)
    solo[1].confidence = 0.3  # very unsure: boxed
    solo[20].confidence = 0.55  # uncertain, far from the other: its own mark
    comp = Composition("k", [Voice("solo", VoiceRole.MELODY, solo, layer="solo")], [Meter(0, 4)],
                       [KeySig(0, 0), KeySig(4 * 96, 3)])
    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), tmp_path / "k.musicxml", band_sounds(arr)).read_text()
    assert "<fifths>5</fifths>" in xml  # A major concert = B major on a B♭ cornet
    assert 'enclosure="rectangle"' in xml and xml.count(">?</words>") >= 2
    assert "#B04A00" in xml.upper() and "#0063A6" in xml.upper()


def test_sharp_minor_keys_get_their_sharps():
    from brasscribe_music.spelling import key_of

    for tonic, name, fifths in ((68, "G#m", 5), (63, "D#m", 6)):
        # harmonic minor up and the tonic triad
        ps = [tonic + i for i in (0, 2, 3, 5, 7, 8, 11, 12, 7, 3, 0)] + [tonic - 12, tonic + 3, tonic + 7] * 3
        du = [4.0] + [1.0] * (len(ps) - 1)
        assert key_of(list(range(len(ps))), du, ps) == (name, fifths)
