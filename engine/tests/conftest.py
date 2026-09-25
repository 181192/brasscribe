"""Fixtures: a temporary data dir, fake adapters (tiny shell scripts) and a two-stage test profile."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from brasscribe_engine import profiles
from brasscribe_engine.config import Settings
from brasscribe_engine.dag import SOURCE, Input, Pipeline, Stage

FAKE_RUN = """#!/bin/sh
# fake adapter: <in> <out>; appends a marker so outputs differ per adapter
set -eu
[ -n "${FAKE_FAIL:-}" ] && { echo boom >&2; exit 3; }
cat "$1" > "$2"
printf '%s' "{name}" >> "$2"
"""


def make_adapters(root: Path) -> Path:
    for name in ("swift-f0", "basic-pitch", "muscriptor"):
        d = root / name
        d.mkdir(parents=True)
        run = d / "run.sh"
        run.write_text(FAKE_RUN.replace("{name}", name))
        run.chmod(run.stat().st_mode | stat.S_IEXEC)
        (d / "pyproject.toml").write_text(f'[project]\nname = "fake-{name}"\nversion = "9.9.9"\n')
    return root


def fake_arrange(ctx) -> None:
    a = ctx.inputs["a"].read_bytes()
    b = ctx.inputs["b"].read_bytes()
    comp = {"title": ctx.params["title"], "voices": [], "meters": [{"tick": 0, "beats": 4, "beat_unit": 4}],
            "keys": [{"tick": 0, "fifths": 0, "mode": "major"}], "beat_times": [], "first_downbeat": 0,
            "ticks_per_beat": 24, "n": len(a) + len(b)}
    (ctx.out / "composition.json").write_text(json.dumps(comp))
    (ctx.out / "brass-band.musicxml").write_text("<score-partwise/>")


def fake_pipeline(title: str, params: dict) -> Pipeline:
    from brasscribe_engine import stages as S

    st = [
        Stage("transcribe.mix.swift-f0", "transcribe", {"audio": Input(SOURCE)}, S.transcribe, adapter="swift-f0",
              params={"output": "mix-sw.mid"}, outputs=("mix-sw.mid",), reuse_subdir="layers"),
        Stage("transcribe.mix.basic-pitch", "transcribe", {"audio": Input(SOURCE)}, S.transcribe, adapter="basic-pitch",
              params={"output": "mix-bp.mid"}, outputs=("mix-bp.mid",), reuse_subdir="layers"),
        Stage("arrange", "arrange", {"a": Input("transcribe.mix.swift-f0", "mix-sw.mid"),
                                     "b": Input("transcribe.mix.basic-pitch", "mix-bp.mid")},
              fake_arrange, params={"title": title}, outputs=("composition.json", "brass-band.musicxml")),
    ]
    outs = {"composition.json": ("arrange", "composition.json"), "brass-band.musicxml": ("arrange", "brass-band.musicxml")}
    return Pipeline("test", "test", st, outs, params)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch) -> Settings:
    adapters = make_adapters(tmp_path / "adapters")
    s = Settings(data_dir=tmp_path / "data", adapters_dir=adapters, gpu_lock=tmp_path / "gpu.lock")
    s.ensure()
    monkeypatch.setitem(profiles.PROFILES, "test", profiles.Profile("test", "test", "fake two-stage profile", False, fake_pipeline))
    monkeypatch.setitem(profiles.DEFAULT_TITLES, "test", "{name} test")
    return s


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    p = tmp_path / "song.wav"
    p.write_bytes(b"RIFF-fake-audio")
    return p
