"""The GPU mutex survives a crashed holder: the kernel drops an OS file lock when its process dies."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from brasscribe_engine.gpulock import file_lock, is_locked

from .test_gpu_wait import run_heavy

HOLD = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from brasscribe_engine.gpulock import file_lock
    with file_lock(Path(sys.argv[1])):
        print("held", flush=True)
        time.sleep(600)
""")


def hold_in_subprocess(path) -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def kill(p: subprocess.Popen) -> None:
    if sys.platform == "win32":
        p.kill()
    else:
        os.kill(p.pid, signal.SIGKILL)  # no cleanup code runs, as in a crash
    p.wait(10)


def test_a_killed_holder_does_not_block_the_next_stage(settings, audio, tmp_path):
    holder = hold_in_subprocess(settings.gpu_lock)
    try:
        assert is_locked(settings.gpu_lock)
        kill(holder)
    finally:
        if holder.poll() is None:
            holder.kill()
    t0 = time.monotonic()
    res, _ = run_heavy(settings, audio, tmp_path, "after-crash")
    assert res.status == "ran"
    assert res.queue_wait_s < 1 and time.monotonic() - t0 < 30
    assert not is_locked(settings.gpu_lock)


def test_a_live_holder_in_another_process_is_waited_for(tmp_path):
    lock = tmp_path / "gpu.lock"
    holder = hold_in_subprocess(lock)
    try:
        blocked = []
        t0 = time.monotonic()
        # Kill the holder while this process waits: the wait ends then, not before.
        import threading
        threading.Timer(0.5, kill, args=(holder,)).start()
        with file_lock(lock, poll=0.02, on_blocked=lambda: blocked.append(1)) as waited:
            assert time.monotonic() - t0 >= 0.45
            assert waited >= 0.45
        assert blocked == [1]
    finally:
        if holder.poll() is None:
            holder.kill()


def test_threads_exclude_each_other(tmp_path):
    import threading
    lock = tmp_path / "gpu.lock"
    inside = 0
    most = 0
    guard = threading.Lock()

    def work():
        nonlocal inside, most
        with file_lock(lock, poll=0.005):
            with guard:
                inside += 1
                most = max(most, inside)
            time.sleep(0.02)
            with guard:
                inside -= 1

    ts = [threading.Thread(target=work) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert most == 1


def test_an_old_style_lock_directory_is_replaced(tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.mkdir()  # left behind by the mkdir lock of an older version
    with file_lock(lock, poll=0.01) as waited:
        assert waited < 1
        assert lock.is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="the pid is informative only")
def test_the_holder_pid_is_in_the_file(tmp_path):
    lock = tmp_path / "gpu.lock"
    with file_lock(lock):
        assert lock.read_text().strip() == str(os.getpid())
