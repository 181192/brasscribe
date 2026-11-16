"""ffmpeg and ffprobe are the environment's own (pixi.toml gives the engine's ffmpeg, which carries ffprobe),
found from the Python that runs, so a run outside `pixi run` cannot quietly decode, or read a recording's length,
with another one on the computer's PATH."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from scribe_music import programs

RUNNER = Path(__file__).resolve().parents[2] / "ml" / "adapters" / "run_adapter.py"
OWN = Path("Library/bin/ffmpeg.exe") if os.name == "nt" else Path("bin/ffmpeg")


def runner_ffmpeg():
    spec = importlib.util.spec_from_file_location("run_adapter_under_test", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner._ffmpeg()


@pytest.mark.parametrize("find", [programs.ffmpeg, runner_ffmpeg])
def test_the_environments_own_comes_first(tmp_path, monkeypatch, find):
    env, elsewhere = tmp_path / "env", tmp_path / "elsewhere"
    (env / OWN).parent.mkdir(parents=True)
    (env / OWN).write_text("")
    (elsewhere / OWN.name).parent.mkdir(parents=True)
    (elsewhere / OWN.name).write_text("#!/bin/sh\n")
    (elsewhere / OWN.name).chmod(0o755)
    monkeypatch.setenv("PATH", str(elsewhere))
    monkeypatch.setattr(sys, "prefix", str(env))
    assert find() == str(env / OWN)
    # Without one of its own, the one on PATH.
    (env / OWN).unlink()
    assert find() == str(elsewhere / OWN.name)


def test_ffprobe_is_found_the_same_way(tmp_path, monkeypatch):
    own = OWN.with_name(OWN.name.replace("ffmpeg", "ffprobe"))
    (tmp_path / own).parent.mkdir(parents=True)
    (tmp_path / own).write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    assert programs.ffprobe() == str(tmp_path / own)


def test_the_engines_environment_has_both():
    """Where the engine runs from its pixi environment (as Bandroom and `pixi run` start it), they are that one's:
    without its ffprobe a beat correction's times could not be checked for a recording libsndfile cannot read."""
    if not (Path(sys.prefix) / "conda-meta").is_dir():
        pytest.skip("not in a pixi environment")
    assert programs.ffmpeg() == str(Path(sys.prefix) / OWN)
    assert programs.ffprobe() == str(Path(sys.prefix) / OWN.with_name(OWN.name.replace("ffmpeg", "ffprobe")))
