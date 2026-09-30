"""The song arrangers (arrange_song, arrange_layers_song): the tune stays out of the accompaniment, and a take
without notes gets a clear message."""

from pathlib import Path

import pretty_midi
import pytest


def _midi(path: Path, notes: list[tuple[int, float, float]]) -> Path:
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(0)
    inst.notes = [pretty_midi.Note(80, p, a, b) for p, a, b in notes]
    pm.instruments.append(inst)
    pm.write(str(path))
    return path


def test_the_melody_stays_out_of_the_harmony(tmp_path):
    from brasscribe_eval.arrange_song import song_composition
    from brasscribe_eval.consensus import doubles

    in_line = doubles([{"pitch": 72, "onset": 1.004}])
    assert in_line({"pitch": 72, "onset": 1.05}) and not in_line({"pitch": 71, "onset": 1.004})
    assert not in_line({"pitch": 72, "onset": 1.2})

    beats = tmp_path / "b.beats"
    beats.write_text("".join(f"{k * 0.5:.3f} {k % 4 + 1}\n" for k in range(32)))
    tune = [(72 + (k % 3), 1.0 + k * 0.5 + 0.004, 1.45 + k * 0.5) for k in range(16)]
    melody = _midi(tmp_path / "mel.mid", tune)
    bass = _midi(tmp_path / "bass.mid", [(36, 1.0 + k, 1.9 + k) for k in range(8)])
    # The harmony stem plays the tune a little late (a real mix is never exact), over a held note.
    harmony = _midi(tmp_path / "harm.mid", [(p, a + 0.03, b) for p, a, b in tune] + [(43, 1.0, 9.0)])
    comp = song_composition(beats, melody, None, bass, [harmony], "t")
    harm = next(v for v in comp.voices if v.id == "harmony")
    assert {n.pitch % 12 for n in harm.notes} == {7}  # the held G only: no C, C# or D from the tune


def test_a_take_without_notes_says_so(tmp_path):
    from brasscribe_eval.arrange_song import song_composition

    beats = tmp_path / "b.beats"
    beats.write_text("".join(f"{k * 0.5:.3f} {k % 4 + 1}\n" for k in range(16)))
    empty = _midi(tmp_path / "empty.mid", [])
    with pytest.raises(SystemExit, match="no notes"):
        song_composition(beats, empty, None, empty, [empty], "t")
    beats.write_text("0.0 1\n")
    with pytest.raises(SystemExit, match="too short"):
        song_composition(beats, empty, None, empty, [empty], "t")


def test_layers_without_notes_say_so(tmp_path):
    from brasscribe_eval import arrange_layers_song as A

    layers = tmp_path / "layers"
    layers.mkdir()
    _midi(layers / "solo-sw.mid", [])
    beats = tmp_path / "b.beats"
    beats.write_text("".join(f"{k * 0.5:.3f} {k % 4 + 1}\n" for k in range(16)))
    args = A.parse_args(["--layers", str(layers), "--beats", str(beats), "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="no notes"):
        A.build(args)
