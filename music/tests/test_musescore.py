"""The machine-wide MuseScore lock: one conversion at a time, and none left behind by a holder that died."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from brasscribe_music import musescore


def test_lock_excludes_and_is_released(tmp_path, monkeypatch):
    monkeypatch.setattr(musescore, "LOCK_FILE", tmp_path / "mscore.flock")
    order = []

    def second():
        with musescore._lock():
            order.append("second")

    with musescore._lock():
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.5)
        order.append("first done")
    t.join(5)
    assert order == ["first done", "second"]
    assert (tmp_path / "mscore.flock").exists()  # the file stays; only the lock on it comes and goes
    with musescore._lock():
        pass


def test_a_cancelled_conversion_kills_musescore_and_stops_waiting_for_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(musescore, "LOCK_FILE", tmp_path / "mscore.flock")
    exe = tmp_path / "mscore"
    exe.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(musescore.Cancelled):
        musescore.convert_many([(tmp_path / "a.musicxml", tmp_path / "a.pdf")], cancel=cancel)
    assert time.monotonic() - started < 10

    with musescore._lock():  # another conversion holds the lock: a cancelled waiter gives up
        with pytest.raises(musescore.Cancelled):
            musescore.convert_many([(tmp_path / "a.musicxml", tmp_path / "a.pdf")], cancel=cancel)


@pytest.mark.skipif(sys.platform == "win32", reason="the launcher here is a shell script")
@pytest.mark.parametrize("stop", ["cancel", "timeout"])
def test_musescore_behind_a_launcher_that_stays_is_stopped_too(tmp_path, monkeypatch, stop):
    """A launcher that starts MuseScore and waits for it (a shell script, `flatpak run`): stopping the
    conversion stops MuseScore itself, not only the launcher."""
    monkeypatch.setattr(musescore, "LOCK_FILE", tmp_path / "mscore.flock")
    pid_file = tmp_path / "pid"
    real = tmp_path / "real-mscore"
    real.write_text(f"#!{sys.executable}\nimport os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n")
    real.chmod(0o755)
    launcher = tmp_path / "mscore"
    launcher.write_text(f'#!/bin/sh\n"{real}" "$@"\necho done\n')  # no exec: the shell stays as the parent
    launcher.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(launcher))
    cancel = threading.Event()

    def stop_when_started():
        while not (pid_file.exists() and pid_file.read_text()):
            time.sleep(0.05)
        cancel.set()

    job = [(tmp_path / "a.musicxml", tmp_path / "a.pdf")]
    if stop == "cancel":
        threading.Thread(target=stop_when_started, daemon=True).start()
        with pytest.raises(musescore.Cancelled):
            musescore.convert_many(job, cancel=cancel)
    else:
        assert musescore.convert_many(job, timeout=3.0) == [(tmp_path / "a.pdf").resolve()]
    pid = int(pid_file.read_text())
    for _ in range(50):  # killed, then reaped by init
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        pytest.fail("MuseScore was left running behind its launcher")


STAND_IN = """#!{python}
# MuseScore as far as a conversion goes: it reads its own folders in the home at start, then writes each output
# of the job. In the user's own home that first read never returns, as on macOS while the system waits for an
# answer to "... would like to access files in your Documents folder".
import json, os, sys, time
home = os.environ.get("CFFIXED_USER_HOME") or os.path.expanduser("~")
if os.path.realpath(home) == os.path.realpath({user_home!r}):
    time.sleep(60)
os.makedirs(os.path.join(home, "Documents", "MuseScore4", "Plugins"), exist_ok=True)
for entry in json.load(open(sys.argv[sys.argv.index("-j") + 1])):
    open(entry["out"], "w").write(home)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in MuseScore here is a script with a #! line")
@pytest.mark.parametrize("platform, own_home", [("darwin", True), ("linux", False)])
def test_on_macos_musescore_runs_in_a_home_of_its_own(tmp_path, monkeypatch, platform, own_home):
    """macOS guards the user's Documents folder per app, and MuseScore reads its plugins there at every start:
    started by an app the user has not answered for, it waits there and writes nothing. In a home of its own it
    has nothing of the user's to read. Elsewhere it keeps the user's home."""
    user_home = tmp_path / "user"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.delenv("CFFIXED_USER_HOME", raising=False)
    monkeypatch.setattr(musescore, "LOCK_FILE", tmp_path / "mscore.flock")
    monkeypatch.setattr(musescore.sys, "platform", platform)
    exe = tmp_path / "mscore"
    exe.write_text(STAND_IN.format(python=sys.executable, user_home=str(user_home)))
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    out = tmp_path / "out" / "a.pdf"
    missing = musescore.convert_many([(tmp_path / "a.musicxml", out)], timeout=30.0 if own_home else 2.0)
    if not own_home:  # in the user's home the stand-in waits, and the conversion ends at its time limit
        assert missing == [out.resolve()]
        return
    assert missing == []
    home = Path(out.read_text())
    assert home != user_home and user_home not in home.parents
    assert not home.exists()  # it lasts as long as the conversion
    assert not (user_home / "Documents").exists()
