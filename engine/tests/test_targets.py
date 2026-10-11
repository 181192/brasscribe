"""Every profile belongs to one target, and a target names its own files."""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest

from scribe_engine import bass_tab, profiles, schemas, tab, targets

SRC = Path(profiles.__file__).resolve().parent
PROFILE_IDS = [p for t in targets.TARGETS.values() for p in t.profiles]


def test_every_profile_is_one_targets_and_every_one_of_a_targets_is_built():
    assert sorted(PROFILE_IDS) == sorted(profiles.PROFILES)
    assert len(set(PROFILE_IDS)) == len(PROFILE_IDS)
    assert {p: profiles.PROFILES[p].target.id for p in PROFILE_IDS} == {
        "solo": "brass", "brass-band": "brass", "pop-rock": "brass", "orchestra-with-soloist": "brass",
        "tab": "fretted", "bass-tab": "fretted"}
    assert set(typing.get_args(schemas.ProfileInfo.model_fields["target"].annotation)) == set(targets.TARGETS)
    with pytest.raises(KeyError):
        targets.of("no-such-profile")


@pytest.mark.parametrize("profile", PROFILE_IDS)
def test_a_run_is_given_the_files_its_target_names(profile):
    target = targets.of(profile)
    pipe = profiles.PROFILES[profile].build("t", {})
    scores = {name for name in pipe.outputs if Path(name).stem in {t.stem for t in targets.TARGETS.values()}}
    assert scores and all(Path(name).stem == target.stem for name in scores)
    assert {target.musicxml, *target.rendered} <= set(pipe.outputs)


def test_the_names_users_get_are_the_ones_they_had():
    assert (targets.BRASS.musicxml, *targets.BRASS.rendered, targets.BRASS.file("mp3"), targets.BRASS.file("brf")) == (
        "brass-band.musicxml", "brass-band.pdf", "brass-band.mid", "brass-band.mp3", "brass-band.brf")
    assert (bass_tab.TAB_JSON, bass_tab.TAB_XML, *targets.FRETTED.rendered, *bass_tab.TEXT_OUTPUTS) == (
        "tab.json", "tab.musicxml", "tab.pdf", "tab.mid", "tab.txt", "tab-instructions.en.txt", "tab-instructions.nb.txt")
    assert tab.is_tab("tab") and tab.is_tab("bass-tab") and not tab.is_tab("solo")


def test_no_shared_code_spells_a_targets_file_name():
    """Outside targets.py a score's file is named through its target: no "brass-band.pdf" or "tab.musicxml" in code.
    Comments and docstrings may still say what a file is called."""
    spelled = re.compile(r'''["'](?:[^"']*/)?(?:brass-band|tab)(?:-instructions)?\.[a-z{]''')
    found = []
    for path in sorted(SRC.glob("*.py")):
        if path.name == "targets.py":
            continue
        code = re.sub(r'""".*?"""', "", path.read_text(), flags=re.S)
        found += [f"{path.name}: {line.strip()}" for line in code.splitlines()
                  if spelled.search(line.split("#")[0])]
    assert found == []
