"""Engine settings: one data directory for models, cache, datasets, uploads and runs.

Every path can be overridden with an environment variable, so the same engine
runs from a checkout, a git worktree (pointing at the main checkout's adapter
environments) or an installed package.

    BRASSCRIBE_DATA         data directory (default: <repo>/data)
    BRASSCRIBE_MODELS       model weights (default: <data>/models, else <repo>/models)
    BRASSCRIBE_ADAPTERS     adapter directory with <name>/run.sh (default: <repo>/ml/adapters)
    BRASSCRIBE_GPU_LOCK     mutex for heavy model runs (default: /tmp/brasscribe-gpu-<uid>.lock; gpulock.py)
    BRASSCRIBE_ADAPTER_TIMEOUT_S  seconds one model run may take before it is stopped (default: 3 hours for
                                  heavy models, 1 hour for the others; adapters.py)
    BRASSCRIBE_TOKEN        optional static bearer token for scripts; Play apps pair and get their own token
    BRASSCRIBE_STATE        companion state: server id and paired devices (default: <data>/companion)
    BRASSCRIBE_DEVICE_IDLE_DAYS  forget a paired device not seen for this many days (default: 180)
    BRASSCRIBE_COMPUTER_NAME     name people know this computer by, for "Brasscribe on <name>"
                                 (default: macOS ComputerName, else the host name)
    BRASSCRIBE_SERVER_NAME       replaces the whole "Brasscribe on <name>" display name
    BRASSCRIBE_TRUST_LOCAL       1 (default): clients on this computer (loopback) use the API without a token.
                                 0: they need a token like any other client. Turn it off whenever something on
                                 this computer forwards outside traffic to the engine (tailscale serve,
                                 cloudflared, a reverse proxy, an SSH tunnel): that traffic looks local.
    BRASSCRIBE_ALLOWED_HOSTS     extra host names, comma-separated, by which clients on this computer may reach the
                                 engine (for a proxy on this computer; guard.py). IP addresses, localhost, .local
                                 names and this computer's host name are always accepted.
    BRASSCRIBE_MAX_UPLOAD_BYTES  largest request body, e.g. an upload, the engine accepts (default: 2 GiB)
    BRASSCRIBE_ADMIN_TOKEN       owner credential for device management (/v1/status, /v1/devices, /v1/pairing*):
                                 `Authorization: Bearer <token>`. While one is set, those endpoints require it
                                 and loopback alone is not enough. It also works on every other endpoint.
    BRASSCRIBE_ADMIN_TOKEN_FILE  read the owner credential from this file instead (created with a random token
                                 if missing; on POSIX it must not be readable by group or others)
    BRASSCRIBE_PARITY_REPORTS       conversion parity reports (default: <repo>/convert/reports, else <repo>/models/convert/reports)
    BRASSCRIBE_CONFORMANCE_REPORTS  core conformance results (default: <data>/runs/core-conformance)
    BRASSCRIBE_BAND_SOUNDS_DIR      the band sounds Studio plays, served at /assets/band/: a folder with
                                    brasscribe-band.sf2 and mapping.json (plus band.json, NOTICE.txt), as
                                    Bandroom bundles it. Unset: whatever the Studio build copied in, if anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .gpulock import default_path

REPO_ROOT = Path(__file__).resolve().parents[3]
# The heavy-model mutex brasscribe_eval also uses: per user, in /tmp on POSIX and the temp folder on Windows.
DEFAULT_GPU_LOCK = default_path()


# Credentials the engine reads from its environment. Programs it starts (adapters, arrangers, MuseScore, the
# conformance suite) never get them: child_env() leaves them out, and `brasscribe serve` removes them from its
# own environment once the app has read them.
CREDENTIAL_ENV = ("BRASSCRIBE_ADMIN_TOKEN", "BRASSCRIBE_ADMIN_TOKEN_FILE", "BRASSCRIBE_TOKEN")


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for a program the engine starts: its own, without the credentials, plus `extra`.
    ONNX Runtime in an adapter reports to Microsoft unless ORT_DISABLE_TELEMETRY is set, so it always is."""
    env = {k: v for k, v in os.environ.items() if k not in CREDENTIAL_ENV}
    return {**env, **(extra or {}), "ORT_DISABLE_TELEMETRY": "1"}


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value not in ("0", "false", "no", "off")


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
    trust_local: bool = field(default_factory=lambda: _env_flag("BRASSCRIBE_TRUST_LOCAL", True))
    allowed_hosts: tuple[str, ...] = field(default_factory=lambda: tuple(
        h.strip() for h in os.environ.get("BRASSCRIBE_ALLOWED_HOSTS", "").split(",") if h.strip()))
    max_upload_bytes: int = field(default_factory=lambda: int(os.environ.get("BRASSCRIBE_MAX_UPLOAD_BYTES") or 2 << 30))
    admin_token: str | None = field(default_factory=lambda: os.environ.get("BRASSCRIBE_ADMIN_TOKEN") or None)
    admin_token_file: Path | None = field(default_factory=lambda: _env_path("BRASSCRIBE_ADMIN_TOKEN_FILE", Path())
                                          if os.environ.get("BRASSCRIBE_ADMIN_TOKEN_FILE") else None)
    # Stages of one job that may run at once when their inputs are ready (at most one on the GPU); 1 runs
    # them one after another in pipeline order.
    # Seconds one model run may take; None: the limit adapters.py sets for heavy and light models.
    adapter_timeout_s: float | None = field(default_factory=lambda: float(os.environ.get("BRASSCRIBE_ADAPTER_TIMEOUT_S") or 0) or None)
    stage_parallelism: int = field(default_factory=lambda: max(1, int(os.environ.get("BRASSCRIBE_STAGE_PARALLELISM") or 1)))
    band_sounds_dir: Path | None = field(default_factory=lambda: _env_path("BRASSCRIBE_BAND_SOUNDS_DIR", Path())
                                         if os.environ.get("BRASSCRIBE_BAND_SOUNDS_DIR") else None)

    def admin_credential(self) -> str | None:
        """The owner credential: `admin_token`, else the contents of `admin_token_file` (created with a random
        token when missing). Refuses a file others can read, so a token another user could copy is never used."""
        if self.admin_token and self.admin_token.strip():
            return self.admin_token.strip()
        path = self.admin_token_file
        if path is None:
            return None
        if not path.exists():
            import secrets

            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32) + "\n")
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise PermissionError(f"{path} is readable by other users; run chmod 600 {path}")
        token = path.read_text().strip()
        if not token:
            raise ValueError(f"{path} is empty")
        return token

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
