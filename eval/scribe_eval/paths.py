"""Repository paths, overridable with the same environment variables as the engine.

    BRASSCRIBE_DATA      data directory (default: <repo>/data)
    BRASSCRIBE_ADAPTERS  adapter directory with <name>/run.sh (default: <repo>/ml/adapters)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("BRASSCRIBE_DATA") or ROOT / "data")
EVAL_SETS = DATA / "eval"
ADAPTERS = Path(os.environ.get("BRASSCRIBE_ADAPTERS") or ROOT / "ml" / "adapters")
