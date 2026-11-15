"""ONNX Runtime runs with its telemetry off: ORT_DISABLE_TELEMETRY is set in the engine, the evaluation and the adapter
runner before anything loads the runtime. Outside Windows the runtime reads it once, as it starts (`import
onnxruntime` is enough): with it set, it never starts its uploader to Microsoft and writes no device id; set later,
it changes nothing."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "ml" / "adapters" / "run_adapter.py"
VARIABLE = "ORT_DISABLE_TELEMETRY"
# The runtime keeps its telemetry off on its own where any of these is set (CI): the tests' children run without them.
CI = ("CI", "TF_BUILD", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "TRAVIS", "JENKINS_URL", "CODEBUILD_BUILD_ID",
      "BUILDKITE", "TEAMCITY_VERSION", "APPVEYOR", "BITBUCKET_BUILD_NUMBER", "ORT_RUNNING_UNIT_TESTS")
LOAD_RUNNER = (f"import importlib.util; s = importlib.util.spec_from_file_location('r', {str(RUNNER)!r}); "
               "s.loader.exec_module(importlib.util.module_from_spec(s))")


def child_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI and k != VARIABLE}
    # Its own home, and no way out: a run with the uploader on queues its events and cannot send them.
    env.update(HOME=str(home), XDG_CACHE_HOME=str(home / ".cache"), USERPROFILE=str(home),
               https_proxy="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", all_proxy="http://127.0.0.1:9")
    return env


def run(python: str, code: str, home: Path) -> str:
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run([python, "-c", code], env=child_env(home), capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize("load", ["import scribe_engine", "import scribe_eval", LOAD_RUNNER])
def test_each_entry_sets_it(tmp_path, load):
    out = run(sys.executable, f"{load}; import os; print(os.environ.get({VARIABLE!r}))", tmp_path)
    assert out.strip() == "1"


def pythons_with_onnxruntime() -> list[str]:
    """The adapters' environments here that have ONNX Runtime (none on a fresh checkout or in CI: then skipped)."""
    found = []
    for py in sorted([*ROOT.glob("ml/adapters/*/.venv/bin/python"), *ROOT.glob(".pixi/envs/*/bin/python")]):
        if subprocess.run([py, "-c", "import onnxruntime"], capture_output=True).returncode == 0:
            found.append(str(py))
    return found


def uploader_state(home: Path) -> list[str]:
    """What the runtime's uploader leaves: its device id and its queue of events."""
    return sorted(p.name for p in home.rglob("*") if ".onnxruntime" in p.parts and p.is_file())


@pytest.mark.skipif(os.name == "nt", reason="on Windows the runtime's events go to ETW; it has no uploader of its own")
@pytest.mark.parametrize("python", pythons_with_onnxruntime() or [pytest.param(None, marks=pytest.mark.skip("no adapter environment with ONNX Runtime"))])
def test_the_runtime_started_by_the_runner_starts_no_uploader(tmp_path, python):
    run(python, "import onnxruntime", tmp_path / "plain")
    if not uploader_state(tmp_path / "plain"):
        pytest.skip("this runtime has no uploader")
    # The runner's variable reaches what it runs: in the same process here, inherited by its adapters.
    run(python, f"{LOAD_RUNNER}; import onnxruntime", tmp_path / "runner")
    assert uploader_state(tmp_path / "runner") == []
