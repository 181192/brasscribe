"""An adapter's environment is ready before the adapter starts (SCRIBE_ENV_LOCKS, envlock.py): a stage waits while
Bandroom installs it, of several stages that need a missing one only the first installs it, and none of this
holds the GPU mutex. Real processes and real locks on both systems (`flock` on POSIX, `LockFileEx` on Windows, where
CI runs this file too), Bandroom's side as it takes it (an exclusive `flock` on the Mac, a .NET `FileStream` with
`FileShare.None` on Windows), and a stand-in `pixi` that records its installs."""

import os
import subprocess
import sys
import textwrap
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from scribe_engine import envlock, gpulock
from scribe_engine.adapters import AdapterCancelled, AdapterError, AdapterRegistry
from scribe_engine.hashing import HashIndex

WINDOWS = sys.platform == "win32"

FAKE_PIXI = textwrap.dedent("""
    import os, sys, time
    from pathlib import Path
    here = Path(__file__).parent
    with open(here / "installs.log", "a") as log:
        log.write(" ".join(sys.argv[1:]) + "\\n")
    time.sleep(float(os.environ.get("FAKE_PIXI_SECONDS", "1")))
    if (here / "FAIL").exists():
        print("error sending request for url")
        sys.exit(1)
    (here / "finished.log").open("a").write(sys.argv[-1] + "\\n")
""")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace with its lockfile, Bandroom's lock folder, and a `pixi` on PATH that logs each install, takes a
    second over it (FAKE_PIXI_SECONDS), logs that it finished, and fails when FAIL is in its folder."""
    root = tmp_path / "envs"
    (root / "ml" / "adapters").mkdir(parents=True)
    (root / "pixi.lock").write_text("version: 6\n")
    locks = root / ".bandroom-setup" / "locks"
    locks.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "fake_pixi.py").write_text(FAKE_PIXI)
    if WINDOWS:
        (bin_dir / "pixi.cmd").write_text(f'@"{sys.executable}" "{bin_dir / "fake_pixi.py"}" %*\r\n')
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    else:
        pixi = bin_dir / "pixi"
        pixi.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{bin_dir / "fake_pixi.py"}" "$@"\n')
        pixi.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("SCRIBE_ENV_LOCKS", str(locks))
    return root, locks, bin_dir


def lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


def installs(bin_dir: Path) -> list[str]:
    return lines(bin_dir / "installs.log")


@contextmanager
def bandroom_holds(path: Path):
    """Bandroom's side, as it takes it: an exclusive flock on the Mac (ModelEnvironments.swift), a .NET FileStream
    with FileShare.None on Windows (EnvironmentLock.cs), here in PowerShell."""
    if WINDOWS:
        script = (f"$f = [System.IO.File]::Open('{path}', 'OpenOrCreate', 'ReadWrite', 'None'); "
                  "[Console]::Out.WriteLine('held'); [Console]::Out.Flush(); [void][Console]::In.ReadLine(); $f.Close()")
        p = subprocess.Popen(["powershell", "-NoProfile", "-Command", script], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
        assert p.stdout.readline().strip() == "held"
        try:
            yield
        finally:
            p.stdin.write("\n")
            p.stdin.close()
            p.wait(timeout=30)
    else:
        import fcntl

        with open(path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield


def bandroom_can_have(path: Path) -> bool:
    """Whether Bandroom could take the lock now (no stage has the environment)."""
    if WINDOWS:
        script = (f"try {{ $f = [System.IO.File]::Open('{path}', 'OpenOrCreate', 'ReadWrite', 'None'); $f.Close(); exit 0 }} "
                  "catch { exit 1 }")
        return subprocess.run(["powershell", "-NoProfile", "-Command", script]).returncode == 0
    import fcntl

    with open(path, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


STAGE = textwrap.dedent("""
    import sys
    from scribe_engine.envlock import environment_ready
    with environment_ready(sys.argv[1], sys.argv[2]):
        print("ran", flush=True)
""")


def stage(env: str, root: Path) -> subprocess.Popen:
    """A stage in a process of its own, as the engine's threads and other engines are to one another."""
    return subprocess.Popen([sys.executable, "-c", STAGE, env, str(root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=os.environ.copy())


def wait_for(check, seconds: float = 30.0) -> None:
    end = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < end, "not within the time"
        time.sleep(0.05)


def test_of_two_stages_that_need_a_missing_environment_only_one_installs_it(workspace):
    root, locks, bin_dir = workspace
    first, second = stage("swift-f0", root), stage("swift-f0", root)
    for p in (first, second):
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0 and out.strip() == "ran", err
    assert len(installs(bin_dir)) == 1 and installs(bin_dir)[0].endswith("--frozen -e swift-f0")
    assert envlock.is_current(locks, "swift-f0", root)
    # Another lockfile: it is installed again.
    (root / "pixi.lock").write_text("version: 6\n# numpy 2.6\n")
    out, _ = stage("swift-f0", root).communicate(timeout=60)
    assert out.strip() == "ran" and len(installs(bin_dir)) == 2


def test_a_stage_waits_while_bandroom_installs_its_environment(workspace):
    root, locks, bin_dir = workspace
    with bandroom_holds(locks / "beat-this.lock"):
        waiting = stage("beat-this", root)
        time.sleep(1.5)
        assert waiting.poll() is None, "the stage went ahead while its environment was being installed"
        envlock._mark(locks, "beat-this", root)  # Bandroom's install ran to its end
    out, err = waiting.communicate(timeout=30)
    assert out.strip() == "ran", err
    assert installs(bin_dir) == []  # it found the environment installed


def test_bandroom_waits_for_the_stages_that_use_an_environment(workspace):
    root, locks, _ = workspace
    envlock._mark(locks, "separator", root)
    with envlock.environment_ready("separator", root) as waited:
        assert waited < 1.0
        assert not bandroom_can_have(locks / "separator.lock")
        # and another stage may use it beside this one
        with envlock.environment_ready("separator", root):
            pass
    assert bandroom_can_have(locks / "separator.lock")


def test_an_install_that_fails_is_named_and_not_marked(workspace):
    root, locks, bin_dir = workspace
    (bin_dir / "FAIL").write_text("")
    with pytest.raises(envlock.EnvironmentNotInstalled, match="could not set up basic-pitch.*error sending request"):
        with envlock.environment_ready("basic-pitch", root):
            pass
    assert not envlock.is_current(locks, "basic-pitch", root)


def test_an_engine_that_ends_during_its_install_ends_the_install_too(workspace, monkeypatch):
    """The engine alone ends while its own install runs (a crash). The install ends with it (a watcher on POSIX, a job
    object on Windows), so it never goes on beside the next engine's; the environment is unmarked, and the next stage
    installs it again, alone."""
    root, locks, bin_dir = workspace
    monkeypatch.setenv("FAKE_PIXI_SECONDS", "4")
    crashing = stage("mega53", root)
    wait_for(lambda: len(installs(bin_dir)) == 1)
    crashing.kill()
    crashing.wait(timeout=30)
    wait_for(lambda: bandroom_can_have(locks / "mega53.lock"), seconds=3)
    time.sleep(4.5)
    assert lines(bin_dir / "finished.log") == [], "the install outlived the engine that started it"
    assert not envlock.is_current(locks, "mega53", root)
    monkeypatch.setenv("FAKE_PIXI_SECONDS", "0.2")
    out, err = stage("mega53", root).communicate(timeout=60)
    assert out.strip() == "ran", err
    assert len(installs(bin_dir)) == 2 and envlock.is_current(locks, "mega53", root)


def test_only_a_held_lock_is_waited_for():
    """LockFileEx says the lock is held with ERROR_LOCK_VIOLATION (or ERROR_IO_PENDING): only that is waited for.
    Any other failure is raised, so a fault never leaves every stage "setting up" for good."""
    assert envlock._lock_busy(True, 0) is True
    assert envlock._lock_busy(False, envlock.ERROR_LOCK_VIOLATION) is False
    assert envlock._lock_busy(False, envlock.ERROR_IO_PENDING) is False
    for fault in (6, 87, 5):  # an invalid handle, an invalid parameter, access denied
        with pytest.raises(OSError, match=f"Windows error {fault}"):
            envlock._lock_busy(False, fault)


def test_only_a_sharing_violation_is_bandroom_holding_the_file():
    """Bandroom for Windows holds the file with no sharing: opening it then fails with ERROR_SHARING_VIOLATION, which
    is waited for. Any other refusal (access denied to a folder, a bad path) is raised, never waited on."""
    assert envlock._not_opened(envlock.ERROR_SHARING_VIOLATION) is None
    for refusal in (5, 3, 123):  # access denied, path not found, a bad name
        with pytest.raises(OSError, match=f"Windows error {refusal}"):
            envlock._not_opened(refusal)


def test_a_heavy_stage_waits_for_its_environment_before_the_gpu_mutex(workspace, tmp_path, monkeypatch):
    root, locks, _ = workspace
    monkeypatch.setenv("SCRIBE_ADAPTER_RUNNER", "pixi")
    adapters = root / "ml" / "adapters"
    (adapters / "run_adapter.py").write_text("import sys; open(sys.argv[3], 'w').write('ok')\n")
    gpu = tmp_path / "gpu.lock"
    registry = AdapterRegistry(adapters, tmp_path / "models", HashIndex(None), gpu_lock=gpu)
    logged, cancel, result = [], threading.Event(), {}

    def job():
        try:
            registry.run("separator", tmp_path / "in.wav", tmp_path / "out", log=logged.append, cancel=cancel)
        except AdapterError as e:
            result["error"] = e

    with bandroom_holds(locks / "separator.lock"):
        t = threading.Thread(target=job)
        t.start()
        wait_for(lambda: any("waiting for this computer to finish setting up separator" in m for m in logged))
        assert not gpulock.is_locked(gpu), "a stage waiting for its environment held the GPU"
        cancel.set()
        t.join(timeout=10)
    assert isinstance(result.get("error"), AdapterCancelled)


def test_the_job_says_which_model_a_stage_waits_for(workspace, tmp_path, monkeypatch):
    """The stage's status names the model while it waits (an app shows "still setting up"), and clears it once the
    stage has it; the wait is not counted against the adapter's time limit."""
    from scribe_engine.jobs import Job

    root, locks, _ = workspace
    monkeypatch.setenv("SCRIBE_ADAPTER_RUNNER", "pixi")
    adapters = root / "ml" / "adapters"
    (adapters / "run_adapter.py").write_text("import sys; open(sys.argv[3], 'w').write('ok')\n")
    registry = AdapterRegistry(adapters, tmp_path / "models", HashIndex(None), gpu_lock=tmp_path / "gpu.lock",
                               timeout_s=5.0)
    job = Job("j1", "solo", None, None, tmp_path / "in.wav", {})
    told, waits = [], []

    def setting_up(model):
        told.append(model)
        job.add_event({"type": "stage", "stage": "beats", "kind": "beats", "status": "started", "setting_up": model})

    def run():
        registry.run("beat-this", tmp_path / "in.wav", tmp_path / "out.beats", setting_up=setting_up, waited=waits.append)

    with bandroom_holds(locks / "beat-this.lock"):
        t = threading.Thread(target=run)
        t.start()
        wait_for(lambda: told == ["beat-this"])
        assert job.stages["beats"]["setting_up"] == "beat-this"
        time.sleep(5.5)  # longer than the time limit: the wait does not count
        envlock._mark(locks, "beat-this", root)
    t.join(timeout=30)
    assert told == ["beat-this", None]
    assert job.stages["beats"]["setting_up"] is None
    assert (tmp_path / "out.beats").read_text() == "ok"
    assert waits and waits[0] >= 5.0


def test_without_the_setting_nothing_is_locked(tmp_path, monkeypatch):
    monkeypatch.delenv("SCRIBE_ENV_LOCKS", raising=False)
    with envlock.environment_ready("beat-this", tmp_path) as waited:
        assert waited == 0.0
    assert list(tmp_path.iterdir()) == []
