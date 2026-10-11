"""Which build of the engine is running: the stamp Bandroom's workspace carries, or the checkout's git commit.

`/v1/health` reports it, so an engine left behind by an app update is visible. Read once per process: from
``.brasscribe-workspace.json`` at the workspace root (the installed copy Bandroom keeps in its data folder), else
``git rev-parse --short HEAD`` in a checkout. None where neither exists (a container image).
"""

from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path

STAMP_FILE = ".brasscribe-workspace.json"

# engine/src/brasscribe_engine/build_info.py -> the workspace or repository root (an editable install).
_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3] if len(_HERE.parents) > 3 else _HERE.parent


def from_stamp(root: Path) -> str | None:
    """"<commit> <stamp[:12]>" from the workspace stamp, or whichever of the two it has."""
    try:
        doc = json.loads((root / STAMP_FILE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    parts = [str(doc[k]) if k == "commit" else str(doc[k])[:12] for k in ("commit", "stamp") if doc.get(k)]
    return " ".join(parts) or None


def from_git(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=2, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


@functools.cache
def build(root: Path = ROOT) -> str | None:
    return from_stamp(root) or from_git(root)
