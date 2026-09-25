"""Engine settings: one data directory for models, cache, datasets, uploads and runs.

Every path can be overridden with an environment variable, so the same engine
runs from a checkout, a git worktree (pointing at the main checkout's adapter
environments) or an installed package.

    BRASSCRIBE_DATA         data directory (default: <repo>/data)
    BRASSCRIBE_MODELS       model weights (default: <data>/models, else <repo>/models)
    BRASSCRIBE_ADAPTERS     adapter directory with <name>/run.sh (default: <repo>/ml/adapters)
    BRASSCRIBE_GPU_LOCK     machine-wide mutex for heavy model runs (default: /tmp/brasscribe-gpu.lock)
    BRASSCRIBE_TOKEN        shared token for LAN clients (default: generated per server start)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_DATA", REPO_ROOT / "data"))
    adapters_dir: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_ADAPTERS", REPO_ROOT / "ml" / "adapters"))
    gpu_lock: Path = field(default_factory=lambda: _env_path("BRASSCRIBE_GPU_LOCK", Path("/tmp/brasscribe-gpu.lock")))
    models_override: Path | None = field(default_factory=lambda: _env_path("BRASSCRIBE_MODELS", Path()) if os.environ.get("BRASSCRIBE_MODELS") else None)
    token: str | None = field(default_factory=lambda: os.environ.get("BRASSCRIBE_TOKEN"))

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

    def ensure(self) -> Settings:
        for d in (self.cache_dir, self.runs_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def load() -> Settings:
    return Settings()
