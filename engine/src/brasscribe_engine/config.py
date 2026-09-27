"""Engine settings: one data directory for models, cache, datasets, uploads and runs.

Every path can be overridden with an environment variable, so the same engine
runs from a checkout, a git worktree (pointing at the main checkout's adapter
environments) or an installed package.

    BRASSCRIBE_DATA         data directory (default: <repo>/data)
    BRASSCRIBE_MODELS       model weights (default: <data>/models, else <repo>/models)
    BRASSCRIBE_ADAPTERS     adapter directory with <name>/run.sh (default: <repo>/ml/adapters)
    BRASSCRIBE_GPU_LOCK     machine-wide mutex for heavy model runs (default: /tmp/brasscribe-gpu.lock)
    BRASSCRIBE_TOKEN        optional static bearer token for scripts; Play apps pair and get their own token
    BRASSCRIBE_STATE        companion state: server id and paired devices (default: <data>/companion)
    BRASSCRIBE_DEVICE_IDLE_DAYS  forget a paired device not seen for this many days (default: 180)
    BRASSCRIBE_COMPUTER_NAME     name people know this computer by, for "Brasscribe on <name>" (default: host name)
    BRASSCRIBE_PARITY_REPORTS       conversion parity reports (default: <repo>/convert/reports, else <repo>/models/convert/reports)
    BRASSCRIBE_CONFORMANCE_REPORTS  core conformance results (default: <data>/runs/core-conformance)
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# The machine-wide mutex other tools also use: /tmp on POSIX, the temp dir on Windows.
DEFAULT_GPU_LOCK = Path(tempfile.gettempdir() if sys.platform == "win32" else "/tmp") / "brasscribe-gpu.lock"


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_DATA", REPO_ROOT / "data"))
    adapters_dir: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_ADAPTERS", REPO_ROOT / "ml" / "adapters"))
    gpu_lock: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_GPU_LOCK", DEFAULT_GPU_LOCK))
    models_override: Path | None = field(default_factory=lambda: _env_path("BRASSCRIBE_MODELS", Path()) if os.environ.get("BRASSCRIBE_MODELS") else None)
    token: str | None = field(default_factory=lambda: os.environ.get("BRASSCRIBE_TOKEN"))
    device_idle_days: float = field(default_factory=lambda: float(os.environ.get("BRASSCRIBE_DEVICE_IDLE_DAYS") or 180))

    @property
    def state_dir(self) -> Path:
        """Server identity and paired devices; kept apart from caches so clearing a cache never unpairs."""
        return _env_path("BRASSCRIBE_STATE", self.data_dir / "companion")

    @property
    def models_dir(self) -> Path:
        if self.models_override:
            return self.models_override
        inside = self.data_dir / "models"
        return inside if inside.exists() else REPO_ROOT / "models"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "eval"

    @property
    def golden_dir(self) -> Path:
        return self.data_dir / "golden"

    @property
    def bench_history_dir(self) -> Path:
        return self.data_dir / "bench" / "history"

    @property
    def parity_reports_dir(self) -> Path:
        """Model-conversion parity reports (JSON): <repo>/convert/reports, else <repo>/models/convert/reports."""
        committed = REPO_ROOT / "convert" / "reports"
        default = committed if committed.is_dir() else REPO_ROOT / "models" / "convert" / "reports"
        return _env_path("BRASSCRIBE_PARITY_REPORTS", default)

    @property
    def conformance_reports_dir(self) -> Path:
        """Rust-core conformance results (JSON), written by the core conformance suite."""
        return _env_path("BRASSCRIBE_CONFORMANCE_REPORTS", self.data_dir / "runs" / "core-conformance")

    def ensure(self) -> Settings:
        for d in (self.cache_dir, self.runs_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def load() -> Settings:
    return Settings()
