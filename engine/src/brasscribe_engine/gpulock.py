"""Machine-wide mutexes held with OS file locks, which the kernel releases when the holder dies.

The GPU mutex used to be an atomic mkdir: a process that crashed while holding it left the
directory behind, and every later heavy stage on the machine waited for it forever. An OS lock
(flock on POSIX, msvcrt.locking on Windows) goes away with the process, however it ends.

The lock file itself stays in place; only the lock on it is taken and dropped. Deleting it while
someone waits on it would let a second process lock a new file of the same name. flock locks
belong to an open file description, so two threads that each open the file exclude each other too.
The holder's pid is written into the file, for people looking at a stuck machine.

The default lock file is per user (/tmp/brasscribe-gpu-<uid>.lock on POSIX, the user's temp folder on
Windows). It is created readable by its owner only, never opened through a symbolic link, and on POSIX
a lock file that belongs to another user is refused.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def default_path() -> Path:
    """The lock file every Brasscribe process of this user shares (brasscribe_eval.gpulock uses the same)."""
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / "brasscribe-gpu.lock"
    return Path("/tmp") / f"brasscribe-gpu-{os.getuid()}.lock"


OPEN_FLAGS = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)


def _checked(fd: int, path: Path) -> int:
    """`fd` if it is a regular file this user owns (POSIX); else it is closed and PermissionError raised."""
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or (hasattr(os, "getuid") and st.st_uid != os.getuid()):
        os.close(fd)
        raise PermissionError(f"{path} is not a lock file of this user; set BRASSCRIBE_GPU_LOCK to another path")
    return fd


def _open(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        # The mkdir lock of an older version. Its holder cannot be checked; an empty one left by a
        # crash is exactly what blocked every stage, so it goes (a live old holder loses the lock).
        try:
            path.rmdir()
            print(f"removed an old-style GPU lock directory at {path}", file=sys.stderr, flush=True)
        except OSError:
            pass
    return _checked(os.open(path, OPEN_FLAGS | os.O_CREAT, 0o600), path)


@contextmanager
def file_lock(path: Path, poll: float = 1.0, on_blocked: Callable[[], None] | None = None) -> Iterator[float]:
    """Hold an exclusive lock on `path`, waiting while another holder has it.

    Yields the seconds spent waiting. `on_blocked` is called once, only if the lock was held.
    """
    path = Path(path)
    t0 = time.monotonic()
    fd = _open(path)
    try:
        blocked = False
        while not _try_lock(fd):
            if not blocked and on_blocked:
                on_blocked()
            blocked = True
            time.sleep(poll)
        waited = time.monotonic() - t0
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, f"{os.getpid()}\n".encode())
        except OSError:
            pass  # the pid is only informative
        try:
            yield waited
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def is_locked(path: Path) -> bool:
    """Whether someone holds the lock on `path` now (for tests and diagnostics)."""
    path = Path(path)
    if not path.is_file():
        return False
    fd = _checked(os.open(path, OPEN_FLAGS), path)
    try:
        if _try_lock(fd):
            _unlock(fd)
            return False
        return True
    finally:
        os.close(fd)
