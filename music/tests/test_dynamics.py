import numpy as np

from brasscribe_music.arranger import arrange_layers
from brasscribe_music.dynamics import layer_dynamics, mark_of
from brasscribe_music.energy import Envelope
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, Dynamic, KeySig, Meter, Note, Voice, VoiceRole

SR = 1000


def test_marks_follow_level():
    assert [mark_of(x) for x in (-35, -25, -18, -12, -6, -1)] == ["pp", "p", "mp", "mf", "f", "ff"]


def test_layer_dynamics_hold_and_change():
    # 8 quiet bars then 8 loud bars (1 s each), with one loud blip in the quiet part.
    y = np.concatenate([0.02 * np.ones(8 * SR), np.ones(8 * SR)]).astype(np.float32) * np.sin(np.arange(16 * SR))
    y[3 * SR:3 * SR + 300] *= 40
    bars = [(k * 96, float(k), float(k + 1)) for k in range(16)]
    ch = layer_dynamics(Envelope.of(y, SR), bars)
    assert ch[0] == (0, "pp") and ch[-1][0] == 8 * 96 and ch[-1][1] in ("f", "ff") and len(ch) == 2


def test_dynamics_are_written_on_the_parts_of_the_layer(tmp_path):
    solo = [Note(72, i * 96, 96) for i in range(8)]
    comp = Composition("d", [Voice("solo", VoiceRole.MELODY, solo, layer="solo")], [Meter(0, 4)], [KeySig(0, 0)],
                       dynamics=[Dynamic(0, "solo", "p"), Dynamic(4 * 96, "solo", "f"), Dynamic(0, "bass", "ff")])
    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), tmp_path / "d.musicxml", band_sounds(arr)).read_text()
    assert xml.count("<p />") + xml.count("<p/>") == 1 and xml.count("<f />") + xml.count("<f/>") == 1
    assert "<ff" not in xml  # the bass layer has no notes here
