"""MuseScore CLI conversions, batched into one launch and serialised machine-wide.

Every launch of the MuseScore 4 CLI on macOS starts the full app (a Dock icon
appears and disappears), so conversions are grouped into a single `-j` job file
and a machine-wide lock keeps at most one instance running at a time.

MuseScore 4.7 aborts during shutdown after writing its output, so success is
judged by the output files existing, never by the exit code.

The binary is `$BRASSCRIBE_MSCORE`, falling back to `mscore` on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Sequence

LOCK_DIR = Path(tempfile.gettempdir()) / "brasscribe-mscore.lock"
STALE_AFTER_S = 900.0
AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac"}

Job = tuple[Path | str, Path | str | Sequence[Path | str]]


def binary() -> str | None:
    return os.environ.get("BRASSCRIBE_MSCORE") or shutil.which("mscore")


def available() -> bool:
    return binary() is not None


@contextmanager
def _lock() -> Iterator[None]:
    while True:
        try:
            LOCK_DIR.mkdir()
            break
        except FileExistsError:
            try:
                if time.time() - LOCK_DIR.stat().st_mtime > STALE_AFTER_S:
                    LOCK_DIR.rmdir()
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            LOCK_DIR.rmdir()
        except FileNotFoundError:
            pass


def convert_many(jobs: Iterable[Job], style: Path | str | None = None, timeout: float = 600.0) -> list[Path]:
    """Run all conversions in one MuseScore launch. Returns the outputs that are missing afterwards."""
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
    with tempfile.TemporaryDirectory() as tmp:
        for i, batch in enumerate(b for b in batches if b):
            job_file = Path(tmp) / f"job{i}.json"
            job_file.write_text(json.dumps(batch))
            cmd = [exe] + (["-S", str(Path(style).resolve())] if style else []) + ["-j", str(job_file)]
            with _lock():
                try:
                    subprocess.run(cmd, capture_output=True, timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
    return [p for p in expected if not p.exists()]


def convert(src: Path | str, out: Path | str | Sequence[Path | str], style: Path | str | None = None,
            timeout: float = 600.0) -> bool:
    """One conversion (possibly to several formats). True when every output was written."""
    return not convert_many([(src, out)], style=style, timeout=timeout)
