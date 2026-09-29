"""Trill notation: sustained two-note alternations written as one note with a trill mark (trills.py)."""

import json
import xml.etree.ElementTree as ET

from brasscribe_music.arranger import arrange
from brasscribe_music.difficulty import apply_difficulty
from brasscribe_music.instruments import MINIMAL_BAND
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Articulation, Composition, KeySig, Meter, Note, Voice, VoiceRole
from brasscribe_music.trills import collapse_trills, timed_runs, with_trills


def _alt(a: int, b: int, n: int, ioi: float, t0: float = 1.0) -> list[dict]:
    return [{"pitch": a if i % 2 == 0 else b, "onset": t0 + i * ioi, "offset": t0 + (i + 1) * ioi} for i in range(n)]


def _runs(notes: list[dict]) -> list[tuple[int, int]]:
    return timed_runs([n["pitch"] for n in notes], [n["onset"] for n in notes], [n["offset"] for n in notes])


def test_runs_need_seven_notes_a_step_apart_and_fast():
    assert _runs(_alt(67, 69, 7, 0.1)) == [(0, 6)]
    assert _runs(_alt(67, 68, 12, 0.08)) == [(0, 11)]
    assert _runs(_alt(67, 69, 6, 0.1)) == []  # two and a half cycles: a figure, not a trill
    assert _runs(_alt(67, 70, 12, 0.08)) == []  # a minor third: a shake, written out
    assert _runs(_alt(60, 72, 12, 0.08)) == []  # an octave lip slur
    assert _runs(_alt(67, 69, 12, 0.2)) == []  # 5 notes/s: a measured alternation


def test_a_held_note_after_the_alternation_is_its_resolution():
    notes = _alt(67, 69, 8, 0.1) + [{"pitch": 67, "onset": 1.8, "offset": 2.8}]
    assert _runs(notes) == [(0, 7)]


def test_a_gap_breaks_the_run():
    notes = _alt(67, 69, 8, 0.1)
    for n in notes:
        n["offset"] -= 0.07  # detached: 70 ms gaps
    assert _runs(notes) == []


def test_with_trills_replaces_the_merged_note_and_keeps_its_held_end():
    line = [{"pitch": 65, "onset": 0.5, "offset": 1.0}, {"pitch": 68, "onset": 1.0, "offset": 3.0}]
    split = [line[0]] + _alt(67, 69, 12, 0.1) + [{"pitch": 67, "onset": 2.2, "offset": 3.0}]
    out = with_trills(line, split)
    assert [(n["pitch"], n["onset"], round(n["offset"], 3), n.get("trill")) for n in out] == [
        (65, 0.5, 1.0, None), (67, 1.0, 2.2, 2), (68, 2.2, 3.0, None)]


def test_with_trills_leaves_a_line_without_alternation_alone():
    line = [{"pitch": 65, "onset": 0.5, "offset": 1.0}]
    assert with_trills(line, line) is line


def _written(a: int, b: int, n: int, step: int = 6, t0: int = 24, seconds: float | None = 0.125) -> list[Note]:
    return [Note(a if i % 2 == 0 else b, t0 + i * step, step, 0.9, ["sw"],
                 onset_s=None if seconds is None else 1 + i * seconds,
                 offset_s=None if seconds is None else 1 + (i + 1) * seconds) for i in range(n)]


def test_collapse_trills_on_written_notes():
    notes = [Note(65, 0, 24, 1.0, ["sw"], 0.5, 1.0)] + _written(69, 67, 16) + [Note(67, 120, 24, 1.0, ["sw"], 3.0, 3.5)]
    out = collapse_trills(notes)
    assert [(n.pitch, n.start, n.dur, n.trill) for n in out] == [(65, 0, 24, None), (67, 24, 96, 2), (67, 120, 24, None)]
    assert out[1].offset_s == 3.0


def test_collapse_trills_without_performed_times_reads_the_grid():
    assert [n.trill for n in collapse_trills(_written(67, 68, 8, seconds=None))] == [1]
    # 8ths are a measured alternation on the page
    assert all(n.trill is None for n in collapse_trills(_written(67, 68, 8, step=12, seconds=None)))


def test_collapse_trills_keeps_chords_and_slow_alternations():
    chords = _written(67, 69, 8) + [Note(60, 24, 6)]
    assert collapse_trills(chords) is chords
    slow = _written(67, 69, 8, seconds=0.25)
    assert collapse_trills(slow) is slow


def _band_comp(melody: list[Note], fifths: int = -1) -> Composition:
    bass = [Note(41, 0, 96), Note(41, 96, 96)]
    return Composition("t", [Voice("m", VoiceRole.MELODY, melody), Voice("b", VoiceRole.BASS, bass)],
                       [Meter(0, 4)], [KeySig(0, fifths)])


def test_difficulty_modes_write_trills():
    lead = MINIMAL_BAND.lead
    parts = {lead: _written(69, 71, 16)}
    assert all(n.trill is None for n in apply_difficulty(parts, MINIMAL_BAND, "faithful")[lead])
    for mode in ("standard", "easier"):
        got = apply_difficulty(parts, MINIMAL_BAND, mode)[lead]
        assert [n.trill for n in got] == [2], mode
    assert [n.trill for n in apply_difficulty(parts, MINIMAL_BAND, "faithful", trills=True)[lead]] == [2]
    assert len(apply_difficulty(parts, MINIMAL_BAND, "standard", trills=False)[lead]) > 1


def test_composition_json_writes_trill_only_where_there_is_one(tmp_path):
    comp = _band_comp([Note(65, 0, 24), Note(69, 24, 48, trill=2, articulations=[Articulation.FERMATA])])
    comp.to_json(tmp_path / "c.json")
    notes = json.loads((tmp_path / "c.json").read_text())["voices"][0]["notes"]
    assert "trill" not in notes[0] and notes[1]["trill"] == 2
    assert [n.trill for n in Composition.from_json(tmp_path / "c.json").voices[0].notes] == [None, 2]


def _ornaments(path, part_name: str) -> list[tuple[str, str | None, list[str]]]:
    """(written step, accidental mark, wavy-line types) of every note with ornaments in a part."""
    root = ET.parse(path).getroot()
    pid = next(sp.get("id") for sp in root.iter("score-part") if sp.findtext("part-name") == part_name)
    part = next(p for p in root.findall("part") if p.get("id") == pid)
    out = []
    for n in part.iter("note"):
        orns = n.findall("notations/ornaments")
        if orns:
            out.append((n.findtext("pitch/step") + (n.findtext("pitch/alter") or ""),
                        next((o.findtext("accidental-mark") for o in orns if o.find("accidental-mark") is not None), None),
                        [w.get("type") for o in orns for w in o.findall("wavy-line")]))
    return out


def test_musicxml_trill_mark_spelled_from_the_written_key(tmp_path):
    # Concert F major: a whole-tone trill on A (auxiliary B natural, not in the key) and a semitone trill on E
    # (auxiliary F, in the key), the second tied over the bar line.
    mel = [Note(65, 0, 24), Note(69, 24, 48, trill=2), Note(64, 72, 48, trill=1), Note(65, 120, 72)]
    comp = _band_comp(mel)
    arr = arrange(comp)
    arr.parts[MINIMAL_BAND.lead] = mel
    path = write_musicxml(build_band_score(arr, comp), tmp_path / "band.musicxml", band_sounds(arr))
    # B-flat cornet, written in G: B with C sharp above it (marked), F sharp with G above it (in the key); each is
    # written as two tied notes, with the wavy line from the first to the last.
    assert _ornaments(path, MINIMAL_BAND.lead) == [("B", "sharp", ["start"]), ("B", None, ["stop"]),
                                                   ("F1", None, ["start"]), ("F1", None, ["stop"])]
    # The trill mark comes first in its <ornaments>, so a wavy line after it reads as the trill's extension.
    root = ET.parse(path).getroot()
    orn = next(o for o in root.iter("ornaments") if o.find("wavy-line") is not None and o.find("trill-mark") is not None)
    assert [c.tag for c in orn] == ["trill-mark", "accidental-mark", "wavy-line"]
