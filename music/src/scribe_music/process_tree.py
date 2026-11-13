"""Stopping a program together with every process it started.

A program is often started through something that stays in between: uv or pixi in front of a model,
a shell script or `flatpak run` in front of MuseScore. Killing only the process that was started
leaves the real one running.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


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


def _clock(text: str) -> float | None:
    """Seconds in ps's processor time: [[days-]hours:]minutes:seconds[.hundredths]."""
    days, _, rest = text.rpartition("-")
    try:
        seconds = 0.0
        for field in rest.split(":"):
            seconds = seconds * 60 + float(field)
        return seconds + 86400 * int(days or 0)
    except ValueError:
        return None


def _proc_seconds(pid: int) -> float | None:
    """One process's user and system time from /proc (Linux), to the clock tick: `ps` rounds to whole seconds,
    which hides the little a starved process gets done on a small machine."""
    try:
        after_name = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
        return (int(after_name[11]) + int(after_name[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def _cpu_seconds_posix(pid: int) -> float | None:
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,time="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    children: dict[int, list[int]] = {}
    used: dict[int, float] = {}
    for line in out.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            seconds = _clock(fields[2])
            if seconds is not None:
                used[int(fields[0])] = seconds
                children.setdefault(int(fields[1]), []).append(int(fields[0]))
    if pid not in used:
        return None
    exact = sys.platform.startswith("linux")
    total, todo = 0.0, [pid]
    while todo:
        p = todo.pop()
        finer = _proc_seconds(p) if exact else None
        total += used[p] if finer is None else finer
        todo += children.get(p, [])
    return total


def _cpu_seconds_windows(pid: int) -> float | None:
    """From the system's process list (who started whom) and each process's own times."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value
    snapshot = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, invalid):
        return None
    children: dict[int, list[int]] = {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        more = k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
            more = k32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snapshot)
    total, todo, seen, read_any = 0.0, [pid], set(), False
    while todo:
        p = todo.pop()
        if p in seen:  # a process id reused by a later process can point back up the list
            continue
        seen.add(p)
        todo += children.get(p, [])
        handle = k32.OpenProcess(0x1000, False, p)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                read_any = True
                total += sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7  # kernel + user
        finally:
            k32.CloseHandle(handle)
    return total if read_any else None


def cpu_seconds(pid: int) -> float | None:
    """Processor time used so far by `pid` and every process below it; None when it cannot be read (the
    process is gone, or the system does not say). Processes that have already exited are not counted, so
    the sum can fall as well as rise."""
    try:
        return _cpu_seconds_windows(pid) if os.name == "nt" else _cpu_seconds_posix(pid)
    except Exception:  # noqa: BLE001 - a reading, never a reason to fail the caller
        return None


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
