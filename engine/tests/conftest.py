"""Fixtures: a temporary data dir, fake adapters (tiny shell scripts) and a two-stage test profile."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brasscribe_engine import profiles
from brasscribe_engine.config import Settings
from brasscribe_engine.dag import SOURCE, Input, Pipeline, Stage

FAKE_RUNNER = """import os, sys
# fake run_adapter.py: <adapter> <in> <out>; copies the input and appends the adapter name
name, src, dst = sys.argv[1:4]
if os.environ.get("FAKE_FAIL"):
    sys.stderr.write("boom")
    sys.exit(3)
with open(src, "rb") as f, open(dst, "wb") as g:
    g.write(f.read() + name.encode())
"""


def make_adapters(root: Path) -> Path:
    for name in ("swift-f0", "basic-pitch", "muscriptor"):
        d = root / name
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text(f'[project]\nname = "fake-{name}"\nversion = "9.9.9"\n')
    (root / "run_adapter.py").write_text(FAKE_RUNNER)
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
    for var in ("BRASSCRIBE_STATE", "BRASSCRIBE_TOKEN", "BRASSCRIBE_DEVICE_IDLE_DAYS"):
        monkeypatch.delenv(var, raising=False)
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
