"""Programs the Python packages call by name, found in the environment they run in first."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _own(name: str) -> str:
    """`name` from the environment this Python runs in, else from PATH."""
    own = Path(sys.prefix) / (f"Library/bin/{name}.exe" if os.name == "nt" else f"bin/{name}")
    return str(own) if own.is_file() else shutil.which(name) or name


def ffmpeg() -> str:
    """The ffmpeg of the environment this Python runs in (the engine's carries one: pixi.toml), else the one on
    PATH, so a run outside `pixi run` still decodes with the same ffmpeg and never quietly with another."""
    return _own("ffmpeg")


def ffprobe() -> str:
    """The ffprobe that comes with ffmpeg(), found the same way."""
    return _own("ffprobe")
