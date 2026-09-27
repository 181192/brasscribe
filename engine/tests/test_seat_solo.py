"""A solo take written for the player's seat (arrange_layers_song --seat), on the frozen ChoraleBricks stems."""

import json
import re
import shutil
from pathlib import Path

import pytest

from brasscribe_eval import arrange_layers_song
from brasscribe_eval.solo_instruments_bench import FIXTURES
from brasscribe_music.arranger import YOUR_RECORDING, arrange_composition, part_sources, place_as_played
from brasscribe_music.instruments import BRASS_BAND, seat_lineup
from brasscribe_music.score_model import Composition, Note

SONG = FIXTURES / "Drese_JesuGehVoran"


def _take(tmp: Path, stem: str, *flags: str) -> tuple[dict, str]:
    layers = tmp / "layers"
    layers.mkdir()
    shutil.copy(SONG / f"{stem}.sw.mid", layers / "solo-sw.mid")
    shutil.copy(SONG / f"{stem}.bp.mid", layers / "solo-bp.mid")
    shutil.copy(SONG / f"{stem}.bp.mid", layers / "solo-mus.mid")
    arrange_layers_song.main(["--layers", str(layers), "--beats", str(SONG / f"{stem}.beats"), "--out", str(tmp / "out"),
                              "--title", stem, "--no-render", "--lineup", "minimal", *flags])
    return json.loads((tmp / "out" / "composition.json").read_text()), (tmp / "out" / "brass-band.musicxml").read_text()


def _names(xml: str) -> list[str]:
    return re.findall(r"<part-name>([^<]*)</part-name>", xml)


def test_baritone_take_is_one_part_in_the_octave_played(tmp_path):
    comp, xml = _take(tmp_path, "04_bar", "--seat", "1st-baritone")
    assert comp["arrangement"]["seat"] == "1st-baritone" and comp["arrangement"]["lead"] == "seat"
    assert "reads" not in comp["arrangement"]
    solo = next(v for v in comp["voices"] if v["id"] == "solo")["notes"]
    assert min(n["pitch"] for n in solo) < 52  # notes below E3 survive the seat's window
    assert _names(xml) == ["1st Baritone"]
    assert "<transpose>" in xml and "<sign>G</sign>" in xml  # treble clef in B♭, the band's default
    c = Composition.from_json(tmp_path / "out" / "composition.json")
    assert part_sources(c) == {"1st Baritone": YOUR_RECORDING}
    arr = arrange_composition(c)  # the phones' re-arrange after an edit keeps the seat
    assert list(arr.parts) == ["1st Baritone"]
    assert [n.pitch for n in arr.parts["1st Baritone"]] == [n["pitch"] for n in solo]


def test_bass_clef_reading_is_concert_pitch(tmp_path):
    comp, xml = _take(tmp_path, "04_tb", "--seat", "1st-trombone", "--reads", "bass")
    assert comp["arrangement"]["reads"] == "bass"
    assert _names(xml) == ["1st Trombone"]
    assert "<transpose>" not in xml and "<sign>F</sign>" in xml and "<sign>G</sign>" not in xml


def test_without_a_seat_nothing_changes(tmp_path):
    comp, xml = _take(tmp_path, "04_bar")
    assert "arrangement" in comp and "seat" not in comp["arrangement"]
    assert _names(xml)[0] == "Solo Cornet" and len(_names(xml)) == 8


def test_seat_errors(tmp_path):
    for flags in (["--seat", "solo-cornet", "--reads", "bass"], ["--lead", "seat"], ["--reads", "bass"]):
        with pytest.raises(SystemExit):
            arrange_layers_song.parse_args(["--layers", "x", "--beats", "y", "--out", "z", *flags])


def test_place_as_played_moves_only_what_is_out_of_range():
    part = seat_lineup("eb-bass").lead_part
    lo, hi = part.instrument.pro
    warnings: list[str] = []
    notes = [Note(40, 0, 24), Note(hi + 12, 24, 24), Note(lo - 1, 48, 24), Note(30, 72, 24)]
    out = place_as_played(notes, part, warnings)
    assert [n.pitch for n in out][0] == 40 and out[3].pitch == 30
    assert lo <= out[1].pitch <= hi and lo <= out[2].pitch <= hi
    assert len(warnings) == 2 and all("E♭ Bass: moved" in w for w in warnings)


def test_seat_lineup_names_the_band_part():
    for seat, name in (("2nd-cornet", "2nd Cornet"), ("solo-horn", "Solo Horn"), ("bass-trombone", "Bass Trombone")):
        lu = seat_lineup(seat)
        assert [p.name for p in lu.parts] == [name] and lu.as_played
        assert lu.parts[0].midi_bank == BRASS_BAND.by_name(name).midi_bank
