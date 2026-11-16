"""An adapter's pixi environment, ready before the adapter starts (SCRIBE_ENV_LOCKS).

Bandroom installs the models' environments behind a running engine. A job that needs one meanwhile must neither
start a second install of it (pixi locks the conda part of an install between processes, not the PyPI part) nor
have it changed under a running model. So every user of an environment goes through one lock file per environment,
`<SCRIBE_ENV_LOCKS>/<environment>.lock`:

- Bandroom holds it exclusively while `pixi install -e <environment>` runs, and then writes the environment's
  marker, `env-<environment>` beside the lock folder, holding the SHA-256 of the pixi.lock it was installed from.
- The engine, before it starts an adapter (and before it takes the GPU mutex, so a download never holds up other
  heavy stages), holds the lock shared while the adapter runs: stages using one environment run side by side, and
  an install waits for them all. When the marker does not match the lockfile, it takes the lock exclusively
  instead, installs the environment itself, writes the marker, and goes on shared; of several stages that need a
  missing environment at once, the first installs it and the rest wait and find it done.

The locks are `flock`s on POSIX and `LockFileEx` locks on Windows, which the system drops when their holder ends.
Bandroom for Windows takes its side by opening the file with no sharing for the length of an install. An install the
engine runs itself ends with the engine (a watcher on POSIX, a job object on Windows), and holds the lock until then. Only a
lock someone holds is waited for; any other failure to take one is raised. Without SCRIBE_ENV_LOCKS, or with the uv
runner, nothing is locked.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from scribe_music.process_tree import kill_tree

INSTALL_LIMIT_S = 3 * 3600.0  # several GB on a slow connection; a stalled install still ends


class EnvironmentNotInstalled(RuntimeError):
    """`pixi install` of an adapter's environment failed: what it said is the message."""


def lock_hash(root: Path) -> str | None:
    lock = Path(root) / "pixi.lock"
    return hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None


def is_current(locks: Path, env: str, root: Path) -> bool:
    """The environment was installed to its end for this workspace's lockfile (its marker says so)."""
    marker = Path(locks).parent / f"env-{env}"
    want = lock_hash(root)
    return want is not None and marker.is_file() and marker.read_text().strip() == want


def _mark(locks: Path, env: str, root: Path) -> None:
    want = lock_hash(root)
    if want is None:
        return
    marker = Path(locks).parent / f"env-{env}"
    part = marker.with_name(marker.name + ".part")
    part.write_text(want)
    os.replace(part, marker)


def _install(env: str, root: Path, cancel: threading.Event | None, poll: float, lock_fd: int | None = None) -> None:
    """`pixi install` of `env`. Should the engine end while it runs, the install ends too, or a stage of the next
    engine would start a second one beside it: on POSIX a watcher ends its process group (and it holds the lock's
    descriptor till then), on Windows it runs in a job object of this process's. Its marker missing, the next stage
    installs it again."""
    pixi = shutil.which("pixi") or "pixi"  # on Windows also pixi.cmd and the like (PATHEXT)
    cmd = [pixi, "install", "--manifest-path", str(Path(root) / "pixi.toml"), "--frozen", "-e", env]
    keep = {}
    if sys.platform != "win32":
        # Under a watcher that ends the install when this process ends, holding the lock till then.
        cmd = [sys.executable, "-c", _WATCHER, str(os.getpid()), *cmd]
        if lock_fd is not None:
            keep = {"pass_fds": (lock_fd,)}
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            **keep)
    job = _ends_with_this_process(proc)
    try:
        end = time.monotonic() + INSTALL_LIMIT_S
        while True:
            try:
                out, _ = proc.communicate(timeout=poll)
                break
            except subprocess.TimeoutExpired:
                if (cancel is not None and cancel.is_set()) or time.monotonic() > end:
                    kill_tree(proc)
                    raise InterruptedError(f"the install of {env} was stopped") from None
            except BaseException:
                kill_tree(proc)
                raise
    finally:
        _close_job(job)
    if proc.returncode != 0:
        raise EnvironmentNotInstalled(f"this computer could not set up {env}: {(out or '')[-2000:]}")


# POSIX has no job objects: the install runs under this watcher, which ends the install and everything it started as
# soon as the engine that started it is gone (its parent is no longer that engine), and otherwise exits as the install
# does. Both stay in the engine's process group, so Bandroom stopping that group stops them as well.
_WATCHER = """
import os, subprocess, sys, time
from scribe_music.process_tree import kill_tree
engine = int(sys.argv[1])
install = subprocess.Popen(sys.argv[2:], close_fds=False)
while install.poll() is None:
    if os.getppid() != engine:
        kill_tree(install)
        sys.exit(1)
    time.sleep(0.2)
sys.exit(install.returncode)
"""

ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33
ERROR_IO_PENDING = 997


def _lock_busy(ok: bool, error: int) -> bool:
    """What a LockFileEx call that asked not to wait says: True when it took the lock, False when someone else holds
    it (ERROR_LOCK_VIOLATION; ERROR_IO_PENDING on a handle opened for overlapped I/O). Any other failure is a fault
    to raise, not a holder to wait for: waiting on it would leave every stage "setting up" for good."""
    if ok:
        return True
    if error in (ERROR_LOCK_VIOLATION, ERROR_IO_PENDING):
        return False
    raise OSError(error, f"LockFileEx failed (Windows error {error})")


if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _Overlapped(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _LockFileEx = _kernel32.LockFileEx
    _LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                            ctypes.POINTER(_Overlapped)]
    _LockFileEx.restype = wintypes.BOOL
    _UnlockFileEx = _kernel32.UnlockFileEx
    _UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
    _UnlockFileEx.restype = wintypes.BOOL
    _EXCLUSIVE, _FAIL_IMMEDIATELY = 0x2, 0x1

    def _lock(fd: int, exclusive: bool, wait: bool) -> bool:
        """LockFileEx on the file's first byte: shared or exclusive, as flock on POSIX."""
        flags = (_EXCLUSIVE if exclusive else 0) | (0 if wait else _FAIL_IMMEDIATELY)
        ok = bool(_LockFileEx(msvcrt.get_osfhandle(fd), flags, 0, 1, 0, ctypes.byref(_Overlapped())))
        return _lock_busy(ok, 0 if ok else ctypes.get_last_error())

    def _unlock(fd: int) -> None:
        if not _UnlockFileEx(msvcrt.get_osfhandle(fd), 0, 1, 0, ctypes.byref(_Overlapped())):
            raise ctypes.WinError(ctypes.get_last_error())

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                   "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _KILL_ON_JOB_CLOSE, _EXTENDED_LIMIT_INFORMATION = 0x2000, 9

    def _ends_with_this_process(proc: subprocess.Popen) -> int | None:
        """A job object that ends `proc` and what it starts when its last handle closes: when this process ends."""
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        if not (_kernel32.SetInformationJobObject(job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
                                                  ctypes.sizeof(limits))
                and _kernel32.AssignProcessToJobObject(job, int(proc._handle))):
            error = ctypes.get_last_error()
            _kernel32.CloseHandle(job)
            kill_tree(proc)
            raise ctypes.WinError(error)
        return job

    def _close_job(job: int | None) -> None:
        if job:
            _kernel32.CloseHandle(job)
else:
    import fcntl

    def _lock(fd: int, exclusive: bool, wait: bool) -> bool:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if wait else fcntl.LOCK_NB))
            return True
        except BlockingIOError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _ends_with_this_process(proc: subprocess.Popen) -> None:
        return None  # the install holds the lock itself (pass_fds in _install)

    def _close_job(job: None) -> None:
        pass


def _not_opened(error: int) -> None:
    """Why the lock file could not be opened on Windows: ERROR_SHARING_VIOLATION is Bandroom holding it for an install
    (it opens it with no sharing), which is waited for (None). Anything else, a real refusal included, is raised."""
    if error == ERROR_SHARING_VIOLATION:
        return None
    raise OSError(error, f"the environment's lock file could not be opened (Windows error {error})")


if sys.platform == "win32":
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.HANDLE]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _GENERIC_READ_WRITE, _SHARE_READ_WRITE, _OPEN_ALWAYS, _NORMAL = 0xC0000000, 0x3, 4, 0x80
    _INVALID_HANDLE = wintypes.HANDLE(-1).value

    def _open(path: Path) -> int | None:
        """The lock file, open (sharing reading and writing, as every stage does); None while Bandroom holds it with no
        sharing. The C runtime's open reports a sharing violation as a plain EACCES, so the file is opened with
        CreateFileW, whose own error tells the two apart."""
        handle = _kernel32.CreateFileW(str(path), _GENERIC_READ_WRITE, _SHARE_READ_WRITE, None, _OPEN_ALWAYS, _NORMAL, None)
        if handle is None or handle == _INVALID_HANDLE:
            return _not_opened(ctypes.get_last_error())
        return msvcrt.open_osfhandle(handle, os.O_RDWR)
else:
    def _open(path: Path) -> int | None:
        """The lock file, open."""
        return os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600)


@contextmanager
def environment_ready(env: str, root: Path, locks: str | os.PathLike | None = None, poll: float = 0.5,
                      on_blocked: Callable[[], None] | None = None,
                      cancel: threading.Event | None = None) -> Iterator[float]:
    """Holds `env` installed and unchanged for the block (see the module). Yields the seconds spent waiting for it,
    an install included. Raises InterruptedError when `cancel` is set first, EnvironmentNotInstalled when the install
    it ran failed."""
    locks = locks if locks is not None else os.environ.get("SCRIBE_ENV_LOCKS")
    if not locks:
        yield 0.0
        return
    path = Path(locks) / f"{env}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    blocked = False

    def wait() -> None:
        nonlocal blocked
        if cancel is not None and cancel.is_set():
            raise InterruptedError(f"cancelled while waiting for {env}")
        if not blocked and on_blocked:
            on_blocked()
        blocked = True
        time.sleep(poll)

    while (fd := _open(path)) is None:
        wait()
    try:
        while True:
            if is_current(path.parent, env, root):
                # Installed: shared, beside any other stage using it; only an install under way holds it up.
                if not _lock(fd, exclusive=False, wait=False):
                    wait()
                    continue
                if is_current(path.parent, env, root):
                    break
                _unlock(fd)  # a new lockfile came in meanwhile
                continue
            # Not installed for this lockfile: exclusive, so that only one installs it, and not under a stage.
            if not _lock(fd, exclusive=True, wait=False):
                wait()
                continue
            try:
                if not is_current(path.parent, env, root):
                    if not blocked and on_blocked:
                        on_blocked()
                    _install(env, root, cancel, poll, lock_fd=fd)
                    _mark(path.parent, env, root)
            finally:
                _unlock(fd)
            # Shared from here (taken again: an install that gets in between finds the environment current and only
            # checks it).
            got = _lock(fd, exclusive=False, wait=False)
            if got and is_current(path.parent, env, root):
                break
            if got:
                _unlock(fd)
            wait()
        try:
            yield time.monotonic() - t0
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
