"""An adapter's environment is ready before the adapter starts (SCRIBE_ENV_LOCKS, envlock.py): a stage waits while
Bandroom installs it, of several stages that need a missing one only the first installs it, and none of this
holds the GPU mutex. Real processes, real `flock`s, and a stand-in `pixi` that records its installs."""

import fcntl
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from scribe_engine import envlock, gpulock
from scribe_engine.adapters import AdapterCancelled, AdapterError, AdapterRegistry
from scribe_engine.hashing import HashIndex

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the lock is POSIX only")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace with its lockfile, Bandroom's lock folder, and a `pixi` on PATH that logs each install, takes a
    second over it and fails when FAIL is in its folder."""
    root = tmp_path / "envs"
    (root / "ml" / "adapters").mkdir(parents=True)
    (root / "pixi.lock").write_text("version: 6\n")
    locks = root / ".bandroom-setup" / "locks"
    locks.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pixi = bin_dir / "pixi"
    pixi.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$*" >> {bin_dir / 'installs.log'}
        sleep 1
        [ -e {bin_dir / 'FAIL'} ] && {{ echo "error sending request for url"; exit 1; }}
        exit 0
    """))
    pixi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("SCRIBE_ENV_LOCKS", str(locks))
    return root, locks, bin_dir


def installs(bin_dir: Path) -> list[str]:
    log = bin_dir / "installs.log"
    return log.read_text().splitlines() if log.exists() else []


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


def test_of_two_stages_that_need_a_missing_environment_only_one_installs_it(workspace):
    root, locks, bin_dir = workspace
    first, second = stage("swift-f0", root), stage("swift-f0", root)
    for p in (first, second):
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0 and out.strip() == "ran", err
    assert installs(bin_dir) == [f"install --manifest-path {root / 'pixi.toml'} --frozen -e swift-f0"]
    assert envlock.is_current(locks, "swift-f0", root)
    # Another lockfile: it is installed again.
    (root / "pixi.lock").write_text("version: 6\n# numpy 2.6\n")
    out, _ = stage("swift-f0", root).communicate(timeout=60)
    assert out.strip() == "ran" and len(installs(bin_dir)) == 2


def test_a_stage_waits_while_bandroom_installs_its_environment(workspace):
    root, locks, bin_dir = workspace
    with open(locks / "beat-this.lock", "a+") as bandroom:
        fcntl.flock(bandroom, fcntl.LOCK_EX)
        waiting = stage("beat-this", root)
        time.sleep(1.0)
        assert waiting.poll() is None, "the stage went ahead while its environment was being installed"
        envlock._mark(locks, "beat-this", root)  # Bandroom's install ran to its end
        fcntl.flock(bandroom, fcntl.LOCK_UN)
    out, _ = waiting.communicate(timeout=30)
    assert out.strip() == "ran"
    assert installs(bin_dir) == []  # it found the environment installed


def test_bandroom_waits_for_the_stages_that_use_an_environment(workspace):
    root, locks, _ = workspace
    envlock._mark(locks, "separator", root)
    with envlock.environment_ready("separator", root) as waited:
        assert waited < 1.0
        with open(locks / "separator.lock", "a+") as bandroom:
            with pytest.raises(BlockingIOError):
                fcntl.flock(bandroom, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # and another stage may use it beside this one
            with envlock.environment_ready("separator", root):
                pass
    with open(locks / "separator.lock", "a+") as bandroom:
        fcntl.flock(bandroom, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_an_install_that_fails_is_named_and_not_marked(workspace):
    root, locks, bin_dir = workspace
    (bin_dir / "FAIL").write_text("")
    with pytest.raises(envlock.EnvironmentNotInstalled, match="could not set up basic-pitch.*error sending request"):
        with envlock.environment_ready("basic-pitch", root):
            pass
    assert not envlock.is_current(locks, "basic-pitch", root)


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

    with open(locks / "separator.lock", "a+") as bandroom:
        fcntl.flock(bandroom, fcntl.LOCK_EX)
        t = threading.Thread(target=job)
        t.start()
        time.sleep(1.0)
        assert not gpulock.is_locked(gpu), "a stage waiting for its environment held the GPU"
        assert any("waiting for this computer to finish setting up separator" in m for m in logged)
        cancel.set()
        t.join(timeout=10)
    assert isinstance(result.get("error"), AdapterCancelled)


def test_without_the_setting_nothing_is_locked(tmp_path, monkeypatch):
    monkeypatch.delenv("SCRIBE_ENV_LOCKS", raising=False)
    with envlock.environment_ready("beat-this", tmp_path) as waited:
        assert waited == 0.0
    assert list(tmp_path.iterdir()) == []


def test_the_job_says_which_model_a_stage_waits_for(workspace, tmp_path, monkeypatch):
    """The stage's status names the model while it waits (an app shows "still setting up"), and clears it once the
    stage has it; the wait is not counted against the adapter's time limit."""
    from scribe_engine.jobs import Job

    root, locks, _ = workspace
    monkeypatch.setenv("SCRIBE_ADAPTER_RUNNER", "pixi")
    adapters = root / "ml" / "adapters"
    (adapters / "run_adapter.py").write_text("import sys; open(sys.argv[3], 'w').write('ok')\n")
    registry = AdapterRegistry(adapters, tmp_path / "models", HashIndex(None), gpu_lock=tmp_path / "gpu.lock",
                               timeout_s=0.5)
    job = Job("j1", "solo", None, None, tmp_path / "in.wav", {})
    told, waits = [], []

    def setting_up(model):
        told.append(model)
        job.add_event({"type": "stage", "stage": "beats", "kind": "beats", "status": "started", "setting_up": model})

    def run():
        registry.run("beat-this", tmp_path / "in.wav", tmp_path / "out.beats", setting_up=setting_up, waited=waits.append)

    with open(locks / "beat-this.lock", "a+") as bandroom:
        fcntl.flock(bandroom, fcntl.LOCK_EX)
        t = threading.Thread(target=run)
        t.start()
        time.sleep(1.0)  # twice the time limit: the wait does not count
        assert job.stages["beats"]["setting_up"] == "beat-this"
        envlock._mark(locks, "beat-this", root)
        fcntl.flock(bandroom, fcntl.LOCK_UN)
    t.join(timeout=30)
    assert told == ["beat-this", None]
    assert job.stages["beats"]["setting_up"] is None
    assert (tmp_path / "out.beats").read_text() == "ok"
    assert waits and waits[0] >= 0.9
