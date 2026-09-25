from fractions import Fraction

from music21 import converter, stream

from brasscribe_music.arranger import arrange_layers
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import (Articulation, Composition, FreeRegion, KeySig, Meter, Note, Voice,
                                          VoiceRole)


def _comp() -> Composition:
    solo = [Note(72, 0, 60), Note(74, 72, 84, articulations=[Articulation.FERMATA]),
            Note(76, 192, 12, performed_dur=4, articulations=[Articulation.STACCATO]), Note(77, 216, 24)]
    bass = [Note(41, 0, 96), Note(36, 96, 96), Note(41, 192, 96)]
    return Composition("free", [Voice("solo", VoiceRole.MELODY, solo, layer="solo"),
                                Voice("bass", VoiceRole.BASS, bass, layer="bass")],
                       [Meter(0, 4)], [KeySig(0, 0)],
                       free_regions=[FreeRegion(0, 192, 0.0, 8.0, 48.0)])


def test_free_region_directions_articulations_and_complete_bars(tmp_path):
    comp = _comp()
    arr = arrange_layers(comp)
    solo = arr.parts["Solo Cornet"]
    assert [a.value for n in solo for a in n.articulations] == ["fermata", "staccato"]
    out = write_musicxml(build_band_score(arr, comp), tmp_path / "free.musicxml", band_sounds(arr))
    xml = out.read_text()
    assert "<staccato" in xml and "<fermata" in xml
    assert "ad lib." in xml and "a tempo" in xml
    assert 'bar-style>dashed' in xml
    assert "<per-minute>48</per-minute>" in xml
    # Every bar of every part is complete (MuseScore drops incomplete measures).
    back = converter.parse(out)
    for p in back.parts:
        for m in p.getElementsByClass(stream.Measure):
            assert Fraction(m.duration.quarterLength) == 4, (p.partName, m.number)
    # Dashed bar lines only inside the region (bar 1 ends inside it; bar 2 ends on its last tick).
    solo_part = next(p for p in back.parts if p.partName == "Solo Cornet")
    styles = [m.rightBarline.type if m.rightBarline else None for m in solo_part.getElementsByClass(stream.Measure)]
    assert styles[0] == "dashed" and styles[1] != "dashed"
