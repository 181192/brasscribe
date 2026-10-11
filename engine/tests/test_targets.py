"""Every profile belongs to one target, and a target names its own files."""

from __future__ import annotations

import ast
import json
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


def _strings(tree: ast.AST):
    """Every string in the code, an f-string as its fixed pieces joined by {}; docstrings left out."""
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add(id(first.value))
    inside = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            inside.update(id(v) for v in node.values)
            yield node.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in inside:
            yield node.lineno, node.value


SPELLED = re.compile(r"(?:^|[/\s(,])(?:brass-band|tab)(?:-instructions)?[.*{]")


def test_the_reader_of_the_code_finds_a_spelled_file_name():
    def found(code: str) -> list[str]:
        return [s for _, s in _strings(ast.parse(code)) if SPELLED.search(s)]

    assert found('x = out / "brass-band.pdf"') == ["brass-band.pdf"]
    assert found('x = f"tab.{ext}" if a else "brass-band" + ".mid"') == ["tab.{}"]  # the bare stem is not found
    assert found('for p in out.glob("tab-instructions.*"): pass') == ["tab-instructions.*"]
    assert found('x = f"{d}/tab.musicxml"; y = "parts/brass-band.brf"') == ["{}/tab.musicxml", "parts/brass-band.brf"]
    assert found('"""writes tab.json"""\nx = "the tab profile"; y = "mix-tab.wav"; z = "bass-tab"') == []


def test_no_engine_code_spells_a_targets_file_name():
    """Outside targets.py no string in the engine's code holds a score's file name: "brass-band.pdf", f"tab.{ext}",
    a glob like "tab-instructions.*", in a concatenation, a conditional or a call alike. Docstrings and comments
    may say what a file is called.

    What this cannot ban: the bare stems "brass-band" and "tab" are also profile ids, so a name put together from
    one ("brass-band" + ".pdf", Path("tab").with_suffix(".pdf")) is not found. Nor does it read the reference
    arrangers and the core's command line, which write the band score's name themselves."""
    found = []
    for path in sorted(SRC.glob("*.py")):
        if path.name == "targets.py":
            continue
        found += [f"{path.name}:{line}: {s!r}" for line, s in _strings(ast.parse(path.read_text())) if SPELLED.search(s)]
    assert found == []


def test_the_benchmarks_gate_the_engines_targets():
    from scribe_eval import suites

    assert set(suites.TARGETS) == set(targets.TARGETS)
    assert {s.target for s in suites.SUITES.values()} == set(targets.TARGETS)


def _kept_run(settings, client, run_id: str, profile: str, files: tuple[str, ...]) -> None:
    """A run on disk as an engine that listed `profile` left it."""
    out = settings.runs_dir / run_id / "outputs"
    out.mkdir(parents=True)
    for name in files:
        (out / name).write_text("<score-partwise/>")
    (settings.runs_dir / run_id / "manifest.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "profile": profile, "pipeline": "x", "title": "t", "params": {}, "status": "succeeded", "input": {"path": "a.wav"},
        "created": "2026-01-01T00:00:00+00:00", "stages": [], "outputs": {name: "0" for name in files}}))


def test_a_run_of_a_profile_the_engine_no_longer_lists_is_still_served(settings):
    from fastapi.testclient import TestClient

    from scribe_engine.api import create_app

    with TestClient(create_app(settings)) as c:
        _kept_run(settings, c, "20260101-000000-big-band-aaaaaa", "big-band", ("brass-band.musicxml",))
        _kept_run(settings, c, "20260101-000001-lute-tab-bbbbbb", "lute-tab", ("tab.musicxml",))
        _kept_run(settings, c, "20260101-000002-nothing-cccccc", "nothing", ())
        band, tab_, none = "20260101-000000-big-band-aaaaaa", "20260101-000001-lute-tab-bbbbbb", "20260101-000002-nothing-cccccc"
        # The target is the one whose score the run wrote, and the score is served under it.
        assert c.get(f"/v1/jobs/{band}").json()["target"] == "brass" and c.get(f"/v1/jobs/{band}/musicxml").status_code == 200
        assert c.get(f"/v1/jobs/{tab_}").json()["target"] == "fretted" and c.get(f"/v1/jobs/{tab_}/musicxml").status_code == 200
        assert c.get(f"/v1/jobs/{band}/pdf").status_code == 404  # not rendered: not there, and not an error
        # A run that wrote no score has no target, and asking for its score is a plain 404.
        assert c.get(f"/v1/jobs/{none}").json()["target"] is None
        for what in ("musicxml", "pdf", "midi", "audio", "braille"):
            assert c.get(f"/v1/jobs/{none}/{what}").status_code == 404, what
        assert {j["id"]: j["target"] for j in c.get("/v1/jobs").json()} == {band: "brass", tab_: "fretted", none: None}
