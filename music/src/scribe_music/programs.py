"""Programs the Python packages call by name, found in the environment they run in first."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def ffmpeg() -> str:
    """The ffmpeg of the environment this Python runs in (the engine's carries one: pixi.toml), else the one on
    PATH, so a run outside `pixi run` still decodes with the same ffmpeg and never quietly with another."""
    own = Path(sys.prefix) / ("Library/bin/ffmpeg.exe" if os.name == "nt" else "bin/ffmpeg")
    return str(own) if own.is_file() else shutil.which("ffmpeg") or "ffmpeg"
