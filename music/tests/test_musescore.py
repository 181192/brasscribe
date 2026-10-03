"""The machine-wide MuseScore lock: one conversion at a time, and none left behind by a holder that died."""

import sys
import threading
import time

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
