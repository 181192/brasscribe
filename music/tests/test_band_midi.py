import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from brasscribe_music.arranger import arrange_layers
from brasscribe_music.instruments import BRASS_BAND, SEAT_OWN_PARTS
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

MAPPING = Path(__file__).resolve().parents[2] / "sounds" / "mapping.json"


def _xml(tmp_path) -> ET.Element:
    solo = [Note(72, i * 24, 24) for i in range(8)]
    bass = [Note(36, i * 96, 96) for i in range(2)]
    strings = [Note(p, 0, 192) for p in (60, 64, 67)]
    drums = [Note(36, 0, 24), Note(42, 0, 12), Note(38, 24, 24), Note(42, 12, 12), Note(49, 96, 24)]
    comp = Composition("m", [Voice("solo", VoiceRole.MELODY, solo, layer="solo"),
                             Voice("bass", VoiceRole.BASS, bass, layer="bass"),
                             Voice("strings", VoiceRole.HARMONY, strings, layer="strings"),
                             Voice("drums", VoiceRole.RHYTHM, drums, layer="drums")], [Meter(0, 4)], [KeySig(0, 0)])
    arr = arrange_layers(comp)
    out = write_musicxml(build_band_score(arr, comp), tmp_path / "m.musicxml", band_sounds(arr))
    raw = out.read_text()
    return ET.fromstring(raw[raw.index("<score-partwise"):])


def test_banks_and_distinct_channels(tmp_path):
    root = _xml(tmp_path)
    banks = {p.name: p.midi_bank for p in BRASS_BAND.parts}
    seen = set()
    for sp in root.iter("score-part"):
        name = sp.findtext("part-name")
        if name == "Percussion":
            continue
        mi = sp.find("midi-instrument")
        assert mi.findtext("midi-bank") == str(banks[name]), name
        assert [c.tag for c in mi][:3] == ["midi-channel", "midi-bank", "midi-program"], name
        dev = sp.find("midi-device")
        key = (dev.get("port") if dev is not None else "1", mi.findtext("midi-channel"))
        assert key[1] != "10" and key not in seen, name
        seen.add(key)
    assert len(seen) == 17


def test_percussion_instruments_per_drum(tmp_path):
    root = _xml(tmp_path)
    sp = next(s for s in root.iter("score-part") if s.findtext("part-name") == "Percussion")
    unpitched = {mi.get("id"): int(mi.findtext("midi-unpitched")) for mi in sp.findall("midi-instrument")}
    assert all(mi.findtext("midi-channel") == "10" for mi in sp.findall("midi-instrument"))
    assert set(unpitched.values()) == {37, 43, 39, 50}  # GM 36 kick, 42 hi-hat, 38 snare, 49 crash, 1-based
    part = next(p for p in root.findall("part") if p.get("id") == sp.get("id"))
    notes = [n for n in part.iter("note") if n.find("unpitched") is not None]
    assert notes and all(n.find("instrument").get("id") in unpitched for n in notes)


@pytest.mark.skipif(not MAPPING.exists(), reason="sounds/mapping.json not available")
def test_banks_match_the_band_soundfont_mapping():
    parts = json.loads(MAPPING.read_text())["parts"]
    for p in [*BRASS_BAND.parts, *SEAT_OWN_PARTS.values()]:
        mx = parts.get(p.name, {}).get("band_soundfont", {}).get("musicxml", {})
        if "midi-bank" in mx:
            assert p.midi_bank == mx["midi-bank"], p.name
            assert p.instrument.gm_program + 1 == mx["midi-program"], p.name
