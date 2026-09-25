import json
from pathlib import Path

import pytest

from brasscribe_music.score_model import (Articulation, Composition, FreeNotation, FreeRegion, KeySig, Meter, Note,
                                          Voice, VoiceRole)

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "mikkel-arranged-band" / "composition.json"


def _comp() -> Composition:
    notes = [Note(72, 0, 48, performed_dur=40), Note(74, 48, 24, performed_dur=8, articulations=[Articulation.STACCATO])]
    return Composition("t", [Voice("solo", VoiceRole.MELODY, notes, layer="solo")], [Meter(0, 4)], [KeySig(0, 0)],
                       [0.0, 1.0, 2.0, 2.5, 3.0], 0,
                       free_regions=[FreeRegion(0, 48, 0.0, 2.0, 60.0, FreeNotation.PROPORTIONAL)])


def test_new_fields_round_trip(tmp_path):
    p = tmp_path / "c.json"
    _comp().to_json(p)
    raw = json.loads(p.read_text())
    assert raw["free_regions"][0] == {"start": 0, "end": 48, "start_s": 0.0, "end_s": 2.0, "tempo_bpm": 60.0,
                                      "notation": "proportional", "label": "ad lib."}
    assert raw["voices"][0]["notes"][1]["articulations"] == ["staccato"]
    back = Composition.from_json(p)
    assert back.free_regions[0].notation is FreeNotation.PROPORTIONAL
    assert back.voices[0].notes[1].articulations == [Articulation.STACCATO]
    assert back.voices[0].notes[0].performed_dur == 40
    assert back.free_region_at(47) is back.free_regions[0] and back.free_region_at(48) is None


def test_old_json_without_new_fields_loads(tmp_path):
    old = {"title": "o", "voices": [{"id": "m", "role": "melody", "notes": [
        {"pitch": 60, "start": 0, "dur": 24, "confidence": 1.0, "sources": [], "onset_s": None, "offset_s": None}]}],
        "meters": [{"tick": 0, "beats": 4, "beat_unit": 4}], "keys": [{"tick": 0, "fifths": 0, "mode": "major"}]}
    p = tmp_path / "old.json"
    p.write_text(json.dumps(old))
    c = Composition.from_json(p)
    assert c.free_regions == [] and c.voices[0].notes[0].articulations == []
    assert c.voices[0].notes[0].performed_dur is None


def test_bpm_ignores_free_regions():
    c = _comp()
    c.beat_times = [0.0, 1.0, 2.0, 2.5, 3.0, 3.5]  # 60 BPM synthetic beats in the region, 120 BPM after
    assert c.bpm == pytest.approx(120.0)


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden output not available")
def test_golden_composition_loads_and_rewrites_losslessly(tmp_path):
    c = Composition.from_json(GOLDEN)
    p = tmp_path / "g.json"
    c.to_json(p)
    old, new = json.loads(GOLDEN.read_text()), json.loads(p.read_text())
    assert new.pop("free_regions") == [] and new.pop("dynamics") == []
    for v in new["voices"]:
        for n in v["notes"]:
            assert n.pop("performed_dur") is None and n.pop("articulations") == []
    assert new == old
