"""MuseScore CLI conversions, batched into one launch and serialised machine-wide.

Every launch of the MuseScore 4 CLI on macOS starts the full app (a Dock icon
appears and disappears), so conversions are grouped into a single `-j` job file
and a machine-wide lock keeps at most one instance running at a time.

MuseScore 4.7 aborts during shutdown after writing its output, so success is
judged by the output files existing, never by the exit code.

A MuseScore that is not getting going (it waits for a folder it may not open, or shows a dialog of its
own) writes nothing and uses no processor time. That is noticed after `START_PATIENCE` seconds instead of
at the conversion's time limit: it is stopped and started once more, since a healthy MuseScore can be held
that long too (macOS checks an app at its first launch after an install or an update, and the app uses no
processor time meanwhile). When the second start does not get going either, `NotStarting` is raised.

On macOS MuseScore runs with a home folder of its own (see `_environment`), so it never opens the
user's Documents folder and never waits for the system to ask permission for it.

The binary is `$SCRIBE_MSCORE`, falling back to `mscore` on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .process_tree import cpu_seconds, kill_tree

LOCK_FILE = Path(tempfile.gettempdir()) / "scribe-mscore.flock"
AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac"}

# How long MuseScore may sit without using the processor before it has written any of its files. A conversion
# at work is busy the whole time (loading, laying out, rendering audio), so it never comes near this.
START_PATIENCE = 30.0
_BUSY = 0.1  # processor seconds that count as having done something

Job = tuple[Path | str, Path | str | Sequence[Path | str]]


def binary() -> str | None:
    return os.environ.get("SCRIBE_MSCORE") or shutil.which("mscore")


def available() -> bool:
    return binary() is not None


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


class Cancelled(RuntimeError):
    """convert_many was told to stop (its `cancel` event was set)."""


class NotStarting(RuntimeError):
    """MuseScore was started, wrote none of its files and used no processor time: it was stopped."""

    def __init__(self, waited: float) -> None:
        super().__init__(f"MuseScore did not get going: after {waited:.0f} s it had written nothing and was not working")


def advice() -> str:
    """What to do about a MuseScore that does not get going, for whoever reads the job's result. The cause is
    not known from here, so nothing is blamed: the first step shows it."""
    opened = ("Open MuseScore once on the computer and check that it starts without asking anything, and that "
              "the folders in its Preferences > Folders exist and can be opened.")
    if sys.platform == "darwin":
        return (f"{opened} If the Mac has asked whether the app that runs the engine may use the Documents "
                "folder, allow it in System Settings > Privacy & Security > Files and Folders.")
    return opened


@contextmanager
def _lock(cancel: threading.Event | None = None) -> Iterator[None]:
    """An OS file lock (flock, msvcrt.locking): the kernel drops it when its holder dies, so a crashed
    conversion never leaves a stale lock that a waiter would have to judge and remove."""
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        while not _try_lock(fd):
            if cancel is not None and cancel.is_set():
                raise Cancelled("MuseScore conversion cancelled")
            time.sleep(0.2)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def _environment(home: Path) -> dict[str, str] | None:
    """The environment MuseScore runs in: on macOS with `home` as its home folder, elsewhere the engine's own.

    MuseScore keeps its plugins, styles and soundfonts in the user's Documents folder and reads them at every
    start, also for a conversion. macOS guards that folder per app, and holds MuseScore's access against the
    app that started the engine. Until the user has answered the system's question for that app, MuseScore
    waits in its first read and writes nothing: the conversion ends at its time limit without a file. With a
    home of its own, MuseScore looks for its Documents and Application Support folders there, and finds them
    empty. Its preferences are not moved (the system keeps them per user, whatever the home): a preference
    that names a folder in the user's Documents still leads MuseScore there."""
    if sys.platform != "darwin":
        return None
    home.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "CFFIXED_USER_HOME": str(home)}


def _run(cmd: list[str], timeout: float, cancel: threading.Event | None, env: dict[str, str] | None = None,
         outputs: Sequence[Path] = (), patience: float | None = None) -> None:
    """MuseScore until it exits, `timeout` passes, or `cancel` is set. Then it is killed with every process
    under it: behind a launcher that stays in between (a shell script, `flatpak run`) MuseScore is not the
    process that was started.

    With `patience`, MuseScore is also stopped, and NotStarting raised, when it has let that many seconds go
    by without using the processor while none of `outputs` exists. Once a file is there it is at work and only
    the time limit applies. Where the processor time cannot be read, nothing is judged."""
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    started = time.monotonic()
    deadline = started + timeout
    busy_at, busy_cpu, next_look = started, 0.0, started + min(2.0, (patience or 2.0) / 4)
    try:
        while True:
            try:
                proc.wait(timeout=0.2)
                return
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                cancelled = cancel is not None and cancel.is_set()
                if cancelled or now > deadline:
                    kill_tree(proc)
                    if cancelled:
                        raise Cancelled("MuseScore conversion cancelled") from None
                    return
                if patience is None or now < next_look:
                    continue
                next_look = now + min(2.0, patience / 4)
                if any(p.exists() for p in outputs):
                    patience = None
                    continue
                used = cpu_seconds(proc.pid)
                if used is None:
                    patience = None
                elif abs(used - busy_cpu) >= _BUSY:  # a fall is a process that finished: something happened
                    busy_at, busy_cpu = now, used
                elif now - busy_at > patience:
                    kill_tree(proc)
                    raise NotStarting(now - started) from None
    except BaseException:  # e.g. Ctrl-C: leave no MuseScore running
        if proc.poll() is None:
            kill_tree(proc)
        raise


def _remove(folder: Path, patience: float = 5.0) -> None:
    """Delete the conversion's folder. What MuseScore leaves running for a moment after it has exited (its
    crash reporter, the system's network storage for it) can still write into the home in there, which makes
    a delete fail or puts a new file there: so it is deleted again until it has stayed gone for a moment."""
    deadline = time.monotonic() + patience
    while True:
        shutil.rmtree(folder, ignore_errors=True)
        time.sleep(0.2)
        if not folder.exists() or time.monotonic() > deadline:
            return


def convert_many(jobs: Iterable[Job], style: Path | str | None = None, timeout: float = 600.0,
                 cancel: threading.Event | None = None) -> list[Path]:
    """Run all conversions in one MuseScore launch. Returns the outputs that are missing afterwards.
    Setting `cancel` stops it: a running MuseScore is killed and Cancelled is raised. A MuseScore that does
    not get going is stopped after START_PATIENCE seconds and started once more; NotStarting is raised when
    that start does not get going either."""
    exe = binary()
    entries: list[dict] = []
    expected: list[Path] = []
    for src, outs in jobs:
        out_list = [outs] if isinstance(outs, (str, Path)) else list(outs)
        paths = [Path(o).resolve() for o in out_list]
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.unlink(missing_ok=True)
        expected += paths
        entries += [{"in": str(Path(src).resolve()), "out": str(p)} for p in paths]
    if not entries:
        return []
    if exe is None:
        return expected
    # MuseScore 4.7 crashes when an audio export follows other exports in the same launch,
    # so notation outputs share one launch and each audio output gets its own.
    audio = [e for e in entries if Path(e["out"]).suffix.lower() in AUDIO_SUFFIXES]
    batches = [[e for e in entries if e not in audio]] + [[e] for e in audio]
    tmp = Path(tempfile.mkdtemp())
    try:
        env = _environment(tmp / "home")
        for i, batch in enumerate(b for b in batches if b):
            job_file = tmp / f"job{i}.json"
            job_file.write_text(json.dumps(batch))
            cmd = [exe] + (["-S", str(Path(style).resolve())] if style else []) + ["-j", str(job_file)]
            outputs = [Path(e["out"]) for e in batch]
            with _lock(cancel):
                try:
                    _run(cmd, timeout, cancel, env, outputs=outputs, patience=START_PATIENCE)
                except NotStarting:  # once more: the first start of a healthy MuseScore can be held this long
                    _run(cmd, timeout, cancel, env, outputs=outputs, patience=START_PATIENCE)
    finally:
        _remove(tmp)
    return [p for p in expected if not p.exists()]


def convert(src: Path | str, out: Path | str | Sequence[Path | str], style: Path | str | None = None,
            timeout: float = 600.0) -> bool:
    """One conversion (possibly to several formats). True when every output was written."""
    return not convert_many([(src, out)], style=style, timeout=timeout)
