"""Stopping a program together with every process it started.

A program is often started through something that stays in between: uv or pixi in front of a model,
a shell script or `flatpak run` in front of MuseScore. Killing only the process that was started
leaves the real one running.
"""

from __future__ import annotations

import os
import signal
import subprocess


def descendants(pid: int) -> list[int]:
    """Every process below `pid` (POSIX, from ps); empty when ps is not there."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit():
            children.setdefault(int(fields[1]), []).append(int(fields[0]))
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child)
    return found


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill a program and every process it started, then reap it. The program stays in the engine's
    process group, so Bandroom stopping the engine's group still stops whatever is running."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass
        proc.kill()
    else:
        # Stop the whole tree first, so nothing in it starts another process while it is being killed: walk it
        # again until a walk finds nothing new (a process started just before its parent stopped).
        stopped: set[int] = set()
        for _ in range(10):
            new = [p for p in [proc.pid, *descendants(proc.pid)] if p not in stopped]
            if not new:
                break
            for p in new:
                try:
                    os.kill(p, signal.SIGSTOP)
                except OSError:
                    pass
            stopped.update(new)
        for p in stopped:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
    try:
        proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        pass
