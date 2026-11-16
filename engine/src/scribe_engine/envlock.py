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

The locks are BSD `flock`s, which the kernel drops when their holder ends. Without SCRIBE_ENV_LOCKS, with the uv
runner, or on Windows (no `flock`), nothing is locked.
"""

from __future__ import annotations

import hashlib
import os
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


def _install(env: str, root: Path, cancel: threading.Event | None, poll: float) -> None:
    cmd = ["pixi", "install", "--manifest-path", str(Path(root) / "pixi.toml"), "--frozen", "-e", env]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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
    if proc.returncode != 0:
        raise EnvironmentNotInstalled(f"this computer could not set up {env}: {(out or '')[-2000:]}")


@contextmanager
def environment_ready(env: str, root: Path, locks: str | os.PathLike | None = None, poll: float = 0.5,
                      on_blocked: Callable[[], None] | None = None,
                      cancel: threading.Event | None = None) -> Iterator[float]:
    """Holds `env` installed and unchanged for the block (see the module). Yields the seconds spent waiting for it,
    an install included. Raises InterruptedError when `cancel` is set first, EnvironmentNotInstalled when the install
    it ran failed."""
    locks = locks if locks is not None else os.environ.get("SCRIBE_ENV_LOCKS")
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if not locks or fcntl is None:
        yield 0.0
        return
    path = Path(locks) / f"{env}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        blocked = False

        def wait() -> None:
            nonlocal blocked
            if cancel is not None and cancel.is_set():
                raise InterruptedError(f"cancelled while waiting for {env}")
            if not blocked and on_blocked:
                on_blocked()
            blocked = True
            time.sleep(poll)

        while True:
            if is_current(path.parent, env, root):
                # Installed: shared, beside any other stage using it; only an install under way holds it up.
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    wait()
                    continue
                if is_current(path.parent, env, root):
                    break
                fcntl.flock(fd, fcntl.LOCK_UN)  # a new lockfile came in meanwhile
                continue
            # Not installed for this lockfile: exclusive, so that only one installs it, and not under a stage.
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                wait()
                continue
            try:
                if not is_current(path.parent, env, root):
                    if not blocked and on_blocked:
                        on_blocked()
                    _install(env, root, cancel, poll)
                    _mark(path.parent, env, root)
            except BaseException:
                fcntl.flock(fd, fcntl.LOCK_UN)
                raise
            # Shared from here. (flock converts by dropping and taking again: an install that gets in between finds
            # the environment current and only checks it.)
            fcntl.flock(fd, fcntl.LOCK_SH)
            break
        try:
            yield time.monotonic() - t0
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
