"""Every part of every lineup resolves in the tables that match on part name."""

import json
from pathlib import Path

import pytest

from brasscribe_engine.talking_score import NB_PART_NAMES
from brasscribe_music.instruments import LINEUPS, part_banks

MAPPING = Path(__file__).resolve().parents[2] / "sounds" / "mapping.json"


def _pitched():
    return [(k, p) for k, lineup in LINEUPS.items() for p in lineup.parts if p.instrument.clef != "percussion"]


def test_every_part_has_an_nb_name_and_a_bank():
    banks = part_banks()
    for key, p in _pitched():
        assert p.name in NB_PART_NAMES, (key, p.name)
        assert p.name in banks, (key, p.name)
    assert NB_PART_NAMES["1st Cornet"] == "1. kornett" and NB_PART_NAMES["Tenor Horn"] == "Althorn"


def test_rust_nb_names_match():
    src = (Path(__file__).resolve().parents[2] / "core" / "scribe-core" / "src" / "talking_score.rs").read_text()
    for name, nb in NB_PART_NAMES.items():
        assert f'"{name}" => "{nb}"' in src, name


@pytest.mark.skipif(not MAPPING.exists(), reason="sounds/mapping.json not available")
def test_every_part_is_in_the_sound_mapping():
    parts = json.loads(MAPPING.read_text())["parts"]
    missing = [p.name for _, p in _pitched() if p.name not in parts]
    assert not missing
    lineups = json.loads(MAPPING.read_text())["lineups"]
    for lineup in LINEUPS.values():
        assert lineups[lineup.name] == [p.name for p in lineup.parts], lineup.name
