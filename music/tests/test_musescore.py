"""The machine-wide MuseScore lock: one conversion at a time, and none left behind by a holder that died."""

import threading
import time

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
