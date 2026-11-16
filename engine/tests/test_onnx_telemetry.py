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


# Windows: the runtime does not read the variable; its events are switched off by a call in the process that runs it.

def load_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_adapter_windows", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("adapter", ["basic-pitch", "separator"])
def test_on_windows_the_adapters_programs_start_with_events_off(tmp_path, monkeypatch, adapter):
    """basic-pitch and the separator run their packages' own programs: on Windows through ort_events_off.py."""
    runner = load_runner()
    monkeypatch.setattr(runner, "WINDOWS", True)
    ran = []
    monkeypatch.setattr(runner, "run", lambda project, cmd, quiet_stderr=True: ran.append(cmd))
    monkeypatch.setattr(runner, "readable", lambda src, tmp: src)
    src = tmp_path / "in.wav"
    src.write_bytes(b"")
    try:
        runner.ADAPTERS[adapter](src, tmp_path / "out")
    except SystemExit:
        pass  # no model ran, so no output: only the command matters here
    assert ran and ran[0][:2] == ["python", str(RUNNER.parent / "ort_events_off.py")]


def test_on_windows_homr_starts_its_program_with_events_off(tmp_path, monkeypatch):
    """homr makes its pages ready first (prepare.py), then runs its program: that command goes through the launcher."""
    runner = load_runner()
    monkeypatch.setattr(runner, "WINDOWS", True)
    monkeypatch.setattr(runner, "homr_setup", lambda: None)
    ran = []
    monkeypatch.setattr(runner, "run", lambda project, cmd, quiet_stderr=True: ran.append(cmd))

    def prepare(cmd, **kwargs):  # writes one ready page where prepare.py would
        out = Path(cmd[cmd.index(str(RUNNER.parent / "homr" / "prepare.py")) + 1])
        (out / "page-1.png").write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", prepare)
    page = tmp_path / "page.png"
    page.write_bytes(b"")
    with pytest.raises(SystemExit):  # no model ran, so no score: only the command matters here
        runner.homr(page, tmp_path / "out.musicxml")
    assert len(ran) == 1
    assert ran[0][:2] == ["python", str(RUNNER.parent / "ort_events_off.py")]
    assert ran[0][2:5] == ["homr", "--gpu", "no"]


def test_elsewhere_the_commands_are_as_they_were():
    runner = load_runner()
    runner.WINDOWS = False
    assert runner.ort_events_off(["homr", "x"]) == ["homr", "x"]


def test_the_launcher_switches_events_off_before_the_program_runs(monkeypatch):
    import importlib.util
    import types

    order = []
    fake = types.ModuleType("onnxruntime")
    fake.disable_telemetry_events = lambda: order.append("off")
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    spec = importlib.util.spec_from_file_location("ort_events_off", RUNNER.parent / "ort_events_off.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    class Entry:
        def load(self):
            return lambda: order.append(("ran", list(sys.argv))) or 0

    monkeypatch.setattr(launcher, "entry_points", lambda group, name: [Entry()] if name == "homr" else [])
    monkeypatch.setattr(sys, "argv", ["x"])
    assert launcher.main(["homr", "--gpu", "no"]) == 0
    assert order == ["off", ("ran", ["homr", "--gpu", "no"])]
    with pytest.raises(SystemExit):
        launcher.main(["nothing-here"])


LAUNCH = """
import importlib.util, sys, types
fake = types.ModuleType("onnxruntime"); fake.disable_telemetry_events = lambda: None; sys.modules["onnxruntime"] = fake
spec = importlib.util.spec_from_file_location("ort_events_off", {launcher!r})
launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
class Entry:
    def load(self):
        return lambda: {result}
launcher.entry_points = lambda group, name: [Entry()]
sys.exit(launcher.main(["program"]))
"""


@pytest.mark.parametrize(("result", "status"), [("None", 0), ("0", 0), ("3", 3), ("'it failed'", 1), ("True", 1)])
def test_the_launcher_exits_as_the_program_would(result, status):
    """What the program's entry point returns is the exit status, as with its own console script: None or 0 is
    success, a number its status, anything else (a message) is printed and is status 1."""
    code = LAUNCH.format(launcher=str(RUNNER.parent / "ort_events_off.py"), result=result)
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == status
