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
    from scribe_eval.arrange_song import song_composition
    from scribe_eval.consensus import doubles

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
    from scribe_eval.arrange_song import song_composition

    beats = tmp_path / "b.beats"
    beats.write_text("".join(f"{k * 0.5:.3f} {k % 4 + 1}\n" for k in range(16)))
    empty = _midi(tmp_path / "empty.mid", [])
    with pytest.raises(SystemExit, match="no notes"):
        song_composition(beats, empty, None, empty, [empty], "t")
    beats.write_text("0.0 1\n")
    with pytest.raises(SystemExit, match="too short"):
        song_composition(beats, empty, None, empty, [empty], "t")


def test_layers_without_notes_say_so(tmp_path):
    from scribe_eval import arrange_layers_song as A

    layers = tmp_path / "layers"
    layers.mkdir()
    _midi(layers / "solo-sw.mid", [])
    beats = tmp_path / "b.beats"
    beats.write_text("".join(f"{k * 0.5:.3f} {k % 4 + 1}\n" for k in range(16)))
    args = A.parse_args(["--layers", str(layers), "--beats", str(beats), "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="no notes"):
        A.build(args)


INVENTED = Path(__file__).resolve().parents[2] / "core" / "conformance" / "fixtures"


def _eighths(tmp_path: Path, bpm: float, per_bar: int, name: str) -> tuple[Path, Path]:
    """A line of eighths, three to the beat (long-short, short-long and three alike), under beats on the dotted
    quarter at `bpm`, `per_bar` of them to the bar."""
    spb = 60 / bpm
    beats = tmp_path / f"{name}.beats"
    beats.write_text("".join(f"{0.5 + k * spb:.3f} {k % per_bar + 1}\n" for k in range(25)))
    shapes = [[0, 1, 2], [0, 2], [0, 1], [0, 1, 2]]
    notes = [(60 + (k + e) % 7, 0.5 + k * spb + e * spb / 3, 0.5 + k * spb + (e + 0.9) * spb / 3)
             for k in range(24) for e in shapes[k % 4]]
    return beats, _midi(tmp_path / f"{name}.mid", notes)


@pytest.mark.parametrize("bpm, per_bar, meter", [(112, 2, (6, 8)), (50, 2, (6, 8)), (80, 4, (12, 8)), (60, 3, (9, 8))])
def test_a_beat_of_three_eighths_is_written_in_compound_time(tmp_path, bpm, per_bar, meter):
    """A tracked beat whose notes divide it in three, two or more to the bar, is the dotted quarter of 6/8, 9/8 or
    12/8: written so, with the eighths as eighths, at any tempo (doubled, it was 2/4 with triplets)."""
    from scribe_eval.arrange_song import song_composition
    from scribe_music.quantize import TICKS_PER_BEAT

    beats, line = _eighths(tmp_path, bpm, per_bar, "line")
    comp = song_composition(beats, line, None, line, [line], "t")
    assert (comp.meters[0].beats, comp.meters[0].beat_unit) == meter
    melody = next(v for v in comp.voices if v.id == "melody").notes
    assert {n.start % (TICKS_PER_BEAT // 2) for n in melody} == {0}  # every note on an eighth, no triplets
    assert comp.first_downbeat == 0 and len(comp.beat_times) > 30  # a quarter-note grid
    assert comp.bpm == pytest.approx(bpm * 1.5, rel=0.02)


def test_a_beat_in_three_the_tracker_calls_a_bar_is_not_compound(tmp_path):
    from scribe_eval.arrange_song import song_composition

    # Every beat a downbeat: a bar counted in one, left to the level rule.
    beats, line = _eighths(tmp_path, 60, 1, "one")
    assert song_composition(beats, line, None, line, [line], "t").meters[0].beat_unit == 4


def test_an_invented_march_in_six_eight_is_written_in_six_eight():
    """A 6/8 march at 112 dotted quarters a minute, played with 12 ms of timing spread on beats with 8 ms of their own:
    its thirds land near the sixteenths often enough that the tab profiles' count (compound) misses it."""
    from scribe_eval.arrange_song import song_composition

    d = INVENTED / "invented-song-6-8-march"
    comp = song_composition(d / "beats.txt", d / "mus.mid", d / "bp.mid", d / "mus.mid", [d / "mus.mid", d / "bp.mid"], "t")
    assert (comp.meters[0].beats, comp.meters[0].beat_unit) == (6, 8)


def test_the_compound_score_reads_six_eight_with_the_beat_on_the_dotted_quarter(tmp_path):
    from scribe_eval.arrange_song import song_composition
    from scribe_music.arranger import arrange_composition
    from scribe_music.musicxml import build_band_score, write_musicxml

    d = INVENTED / "invented-song-6-8"
    comp = song_composition(d / "beats.txt", d / "mus.mid", d / "bp.mid", d / "mus.mid", [d / "mus.mid", d / "bp.mid"], "t")
    xml = write_musicxml(build_band_score(arrange_composition(comp), comp), tmp_path / "s.musicxml").read_text()
    assert "<beats>6</beats>" in xml and "<beat-type>8</beat-type>" in xml
    assert "<beat-unit-dot />" in xml and "<per-minute>50</per-minute>" in xml and 'tempo="75"' in xml
    assert "<time-modification>" not in xml  # no triplets
