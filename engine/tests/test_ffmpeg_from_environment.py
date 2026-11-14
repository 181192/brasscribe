"""ffmpeg is the environment's own (pixi.toml gives the engine's one), found from the Python that runs, so a run
outside `pixi run` cannot quietly decode with another ffmpeg on the computer's PATH."""

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


def test_the_engines_environment_has_one():
    """Where the engine runs from its pixi environment (as Bandroom and `pixi run` start it), it is that one."""
    if not (Path(sys.prefix) / "conda-meta").is_dir():
        pytest.skip("not in a pixi environment")
    assert programs.ffmpeg() == str(Path(sys.prefix) / OWN)
