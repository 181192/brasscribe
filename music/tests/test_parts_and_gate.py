import xml.etree.ElementTree as ET

import numpy as np

from brasscribe_music.arranger import arrange_layers
from brasscribe_music.durations import written_durations
from brasscribe_music.energy import Envelope, gate
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.parts import split_parts
from brasscribe_music.quantize import BeatMap, QNote
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole


def test_gate_drops_notes_where_the_layer_is_silent():
    sr = 1000
    y = np.zeros(4 * sr, dtype=np.float32)
    y[sr:2 * sr] = 0.5 * np.sin(np.arange(sr) * 0.3)  # sound only between 1 and 2 s
    env = Envelope.of(y, sr)
    kept, dropped = gate([{"onset": 0.5}, {"onset": 1.2}, {"onset": 3.0}], env)
    assert [n["onset"] for n in kept] == [1.2] and dropped == 2


def test_part_writing_options_make_staccato_eighths():
    bm = BeatMap(np.arange(0, 10, 0.5))
    notes = [QNote(60, 0, 6, 0.0, 0.05), QNote(62, 12, 18, 0.25, 0.3), QNote(64, 48, 54, 1.0, 1.05)]
    default = written_durations(notes, bm)
    parts = written_durations(notes, bm, hold_within=12, min_detached=12)
    assert [w.dur for w in default] == [6, 6, 6]
    assert [w.dur for w in parts] == [12, 12, 12] and all(w.staccato for w in parts)


def test_parts_have_one_part_multi_rests_tempo_and_tacet(tmp_path):
    from brasscribe_music.score_model import Section
    solo = [Note(72, 0, 96), Note(74, 5 * 96, 96), Note(74, 12 * 96, 96)]
    comp = Composition("t", [Voice("solo", VoiceRole.MELODY, solo, layer="solo")], [Meter(0, 4)], [KeySig(0, 0)],
                       [0.5 * i for i in range(60)], sections=[Section(8 * 96, "A")])
    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), tmp_path / "band.musicxml", band_sounds(arr))
    files = split_parts(xml, tmp_path / "parts")
    assert len(files) == len(arr.lineup.parts)
    solo_file = next(f for f in files if "Solo-Cornet" in f.name)
    root = ET.fromstring(solo_file.read_text().partition("<score-partwise")[1] + solo_file.read_text().partition("<score-partwise")[2])
    assert len(root.findall("part")) == 1
    assert [m.text for m in root.iter("multiple-rest")] == ["4", "2", "4"]  # bars 2-5, 7-8, then 9-12 after letter A
    assert [r.text for r in root.iter("rehearsal")] == ["A"]
    horn = next(f for f in files if "Solo-Horn" in f.name).read_text()
    assert "<per-minute>" in horn  # tempo copied from the top part
    assert "(Tacet)" in next(f for f in files if "Soprano" in f.name).read_text()
