"""The machine-wide heavy-model lock the engine uses (BRASSCRIBE_GPU_LOCK), for live eval runs.

The engine's OS file lock (brasscribe_engine.gpulock) when the engine is installed, as in the pixi
environment; otherwise the same flock on the same file (POSIX), so both exclude each other. The
kernel drops the lock when the holder dies, so a crashed run cannot block the GPU.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

GPU_LOCK = Path(os.environ.get("BRASSCRIBE_GPU_LOCK", "/tmp/brasscribe-gpu.lock"))


@contextmanager
def gpu_lock(poll: float = 1.0) -> Iterator[None]:
    try:
        from brasscribe_engine.gpulock import file_lock
    except ImportError:
        file_lock = None
    if file_lock is not None:
        with file_lock(GPU_LOCK, poll=poll):
            yield
        return
    import fcntl

    if GPU_LOCK.is_dir():
        try:
            GPU_LOCK.rmdir()  # the mkdir lock of an older version
        except OSError:
            pass
    fd = os.open(GPU_LOCK, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(poll)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
