"""Model adapters: subprocesses behind the `<input> <output>` contract.

Each adapter lives in `<adapters_dir>/<name>/` with its own environment (uv
project, or the pixi environment of the same name when
BRASSCRIBE_ADAPTER_RUNNER=pixi). The engine never imports model code; it runs
`<adapters_dir>/run_adapter.py <name> <input> <output>` with its own Python (the
same runner every run.sh delegates to, so it works on Windows too; an adapter
dir without the runner falls back to run.sh) and records what ran:

  fingerprint  digest of the adapter's pyproject, lockfile and scripts
  version      the adapter project version
  models       weights the adapter reads, with sha256 (or a hub revision)
  device       the accelerator the adapter will use on this host

Heavy adapters (large models on long audio) take the machine-wide GPU mutex.
"""

from __future__ import annotations

import os
import platform
import sys
import shutil
import subprocess
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .gpulock import file_lock
from .hashing import HashIndex, sha256_bytes


@dataclass(frozen=True)
class Adapter:
    name: str
    heavy: bool
    accelerator: str  # "torch", "coreml-or-onnx", "cpu"
    model_files: tuple[str, ...] = ()  # relative to the models dir
    hub_models: tuple[str, ...] = ()  # Hugging Face repo ids read from the local hub cache
    torch_checkpoints: tuple[str, ...] = ()  # files in ~/.cache/torch/hub/checkpoints
    env: tuple[tuple[str, str], ...] = ()  # default environment for run.sh
    scripts: tuple[str, ...] = ("pyproject.toml", "uv.lock", "run.sh")
    licence: str | None = None  # weights licence as recorded in docs/plan/apps-plan.md §7
    dir: str | None = None  # adapter directory when it differs from the name
    entry: str = "run.sh"  # script with the <input> <output> contract


ADAPTERS: dict[str, Adapter] = {
    a.name: a
    for a in [
        Adapter("beat-this", heavy=True, accelerator="torch", torch_checkpoints=("beat_this-final0.ckpt",),
                licence="MIT"),
        Adapter("mega53", heavy=True, accelerator="torch",
                model_files=("mega53/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", "mega53/mvsep_mega_model_bs_roformer_53_stems.yaml"),
                scripts=("pyproject.toml", "uv.lock", "run.sh", "setup.sh"), licence="not stated"),
        Adapter("separator", heavy=True, accelerator="torch", model_files=("separator/BS-Roformer-SW.ckpt", "separator/BS-Roformer-SW.yaml"),
                licence="not stated"),
        Adapter("muscriptor", heavy=True, accelerator="torch", hub_models=("MuScriptor/muscriptor-medium",),
                env=(("MUSCRIPTOR_MODEL", "medium"),), licence="CC BY-NC 4.0"),
        Adapter("basic-pitch", heavy=False, accelerator="coreml-or-onnx", licence="Apache-2.0"),
        Adapter("swift-f0", heavy=False, accelerator="cpu", scripts=("pyproject.toml", "uv.lock", "run.sh", "transcribe.py"),
                licence="MIT"),
        Adapter("swift-f0-contour", heavy=False, accelerator="cpu", dir="swift-f0", entry="contour.sh",
                scripts=("pyproject.toml", "uv.lock", "contour.sh", "contour.py"), licence="MIT"),
    ]
}


def host_device() -> str:
    """Accelerator a torch adapter uses on this host: cuda, mps or cpu."""
    if os.environ.get("BRASSCRIBE_DEVICE"):
        return os.environ["BRASSCRIBE_DEVICE"]
    if shutil.which("nvidia-smi"):
        try:
            if subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=10).returncode == 0:
                return "cuda"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mps"
    return "cpu"


def adapter_device(adapter: Adapter) -> str:
    if adapter.accelerator == "torch":
        return host_device()
    if adapter.accelerator == "coreml-or-onnx":
        return "coreml" if platform.system() == "Darwin" else "onnx-cpu"
    return "cpu"


class AdapterError(RuntimeError):
    pass


class HeavyRunRefused(AdapterError):
    """A heavy model would have to run, but the run was started with heavy runs disabled."""


@dataclass
class AdapterRegistry:
    root: Path
    models_dir: Path
    hashes: HashIndex
    gpu_lock: Path = Path("/tmp/brasscribe-gpu.lock")
    _fingerprints: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> Adapter:
        if name not in ADAPTERS:
            raise KeyError(f"unknown adapter {name!r}")
        return ADAPTERS[name]

    def dir(self, name: str) -> Path:
        return self.root / (self.get(name).dir or name)

    def script(self, name: str) -> Path:
        return self.dir(name) / self.get(name).entry

    def fingerprint(self, name: str) -> str:
        if name not in self._fingerprints:
            a = self.get(name)
            parts = []
            for rel in a.scripts:
                p = self.dir(name) / rel
                parts.append(f"{rel}:{sha256_bytes(p.read_bytes()) if p.exists() else '-'}")
            runner = self.root / "run_adapter.py"
            if runner.exists():
                parts.append(f"run_adapter.py:{sha256_bytes(runner.read_bytes())}")
            parts.extend(f"{k}={v}" for k, v in a.env)
            self._fingerprints[name] = sha256_bytes("\n".join(parts).encode())
        return self._fingerprints[name]

    def version(self, name: str) -> str | None:
        p = self.dir(name) / "pyproject.toml"
        if not p.exists():
            return None
        return tomllib.loads(p.read_text()).get("project", {}).get("version")

    def models(self, name: str) -> list[dict]:
        a = self.get(name)
        out = []
        for rel in a.model_files:
            p = self.models_dir / rel
            out.append({"name": rel, "sha256": self.hashes.file(p) if p.exists() else None, "present": p.exists(),
                        "bytes": p.stat().st_size if p.exists() else None, "licence": a.licence})
        hub = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
        for repo in a.hub_models:
            ref = hub / f"models--{repo.replace('/', '--')}" / "refs" / "main"
            out.append({"name": repo, "revision": ref.read_text().strip() if ref.exists() else None,
                        "present": ref.exists(), "licence": a.licence})
        ckpts = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
        for f in a.torch_checkpoints:
            p = ckpts / f
            out.append({"name": f, "sha256": self.hashes.file(p) if p.exists() else None, "present": p.exists(),
                        "bytes": p.stat().st_size if p.exists() else None, "licence": a.licence})
        return out

    def describe(self, name: str) -> dict:
        a = self.get(name)
        return {"name": name, "version": self.version(name), "fingerprint": self.fingerprint(name),
                "heavy": a.heavy, "device": adapter_device(a), "licence": a.licence, "models": self.models(name)}

    gpu_poll = 1.0  # seconds between tries while another process holds the GPU mutex

    @contextmanager
    def gpu_mutex(self, poll: float | None = None, on_blocked: Callable[[], None] | None = None):
        """Machine-wide lock on `gpu_lock` (an OS file lock: it excludes other processes and other
        threads alike, and the kernel drops it when the holder dies, so a crash cannot block the GPU).
        Yields the seconds spent waiting; `on_blocked` is called once, only if the lock was held."""
        with file_lock(self.gpu_lock, poll=self.gpu_poll if poll is None else poll, on_blocked=on_blocked) as waited:
            yield waited

    def run(self, name: str, src: Path, dst: Path, env: dict[str, str] | None = None, allow_heavy: bool = True,
            log=None, waited: Callable[[float], None] | None = None) -> float:
        """Run an adapter; returns wall-clock seconds, including any wait for the GPU mutex, which is
        also reported to `waited` (heavy adapters only)."""
        a = self.get(name)
        if a.heavy and not allow_heavy:
            raise HeavyRunRefused(f"{name} would run on {src.name}, but heavy runs are disabled (cache miss)")
        runner = self.root / "run_adapter.py"
        if runner.exists():
            cmd = [sys.executable, str(runner), name, str(src), str(dst)]
        elif self.script(name).exists():
            cmd = [str(self.script(name)), str(src), str(dst)]
        else:
            raise AdapterError(f"no run_adapter.py or {self.script(name)}")
        full_env = {**os.environ, **dict(a.env), **(env or {})}
        t0 = time.time()

        def call():
            # the engine's own stdin may be a closed terminal; Python children abort on a dead fd 0
            proc = subprocess.run(cmd, env=full_env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            if proc.returncode != 0:
                raise AdapterError(f"{name} failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-2000:]}")

        if a.heavy:
            def blocked():
                if log:
                    log(f"{name}: waiting for GPU mutex {self.gpu_lock}")

            with self.gpu_mutex(on_blocked=blocked) as wait:
                if waited:
                    waited(wait)
                if log and wait >= 1.0:
                    log(f"{name}: got GPU mutex after {wait:.1f} s")
                call()
        else:
            call()
        return time.time() - t0
