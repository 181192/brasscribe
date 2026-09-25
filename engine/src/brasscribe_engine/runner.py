"""Run one job: build the profile's DAG, execute it, write the run directory and manifest.

    <data>/runs/<run-id>/
        manifest.json    what ran: profile, params, input hash, git SHA, host, device,
                         per-stage cache key / status / adapter version / model hashes
        events.jsonl     progress events as streamed over SSE
        stages/<stage>/  each stage's files (hardlinks into the cache)
        outputs/         final files: composition.json, brass-band.musicxml/.pdf/.mid/.mp3
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__, profiles
from .adapters import AdapterRegistry, host_device
from .cache import ArtifactCache, link_or_clone
from .config import REPO_ROOT, Settings
from .dag import Cancelled, Executor, StageFailed
from .hashing import HashIndex

MANIFEST_SCHEMA = 1


class RunRefused(ValueError):
    pass


def new_run_id(profile: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{profile}-{uuid.uuid4().hex[:6]}"


def git_state(root: Path = REPO_ROOT) -> dict:
    def git(*args: str) -> str | None:
        try:
            p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    status = git("status", "--porcelain", "--untracked-files=no")
    return {"sha": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def host_info() -> dict:
    return {"system": platform.system(), "machine": platform.machine(), "python": sys.version.split()[0],
            "device": host_device(), "engine": __version__}


def check_out_dir(out: Path, settings: Settings) -> None:
    out = Path(out).resolve()
    golden = settings.golden_dir.resolve()
    if out == golden or golden in out.parents:
        raise RunRefused(f"refusing to write into the golden output directory {golden}")


def _session(settings: Settings) -> tuple[ArtifactCache, AdapterRegistry]:
    settings.ensure()
    hashes = HashIndex(settings.cache_dir / "file-hashes.json")
    cache = ArtifactCache(settings.cache_dir, hashes)
    adapters = AdapterRegistry(settings.adapters_dir, settings.models_dir, hashes, settings.gpu_lock)
    return cache, adapters


def run(settings: Settings, audio: Path, profile: str, *, title: str | None = None, params: dict | None = None,
        out: Path | None = None, reuse: Path | None = None, allow_heavy: bool = True, cold: set[str] | None = None,
        run_id: str | None = None, emit: Callable[[dict], None] | None = None,
        cancel: threading.Event | None = None, previous_run_id: str | None = None) -> dict:
    audio = Path(audio).resolve()
    if not audio.exists():
        raise FileNotFoundError(audio)
    if out is not None:
        check_out_dir(out, settings)
    pipeline = profiles.build(profile, audio, title, params)
    run_id = run_id or new_run_id(profile)
    run_dir = settings.runs_dir / run_id
    check_out_dir(run_dir, settings)
    run_dir.mkdir(parents=True, exist_ok=True)
    cache, adapters = _session(settings)
    events_file = (run_dir / "events.jsonl").open("a")
    seq = [0]

    def on_event(e: dict) -> None:
        seq[0] += 1
        e = {"id": seq[0], "run": run_id, **e}
        events_file.write(json.dumps(e) + "\n")
        events_file.flush()
        if emit:
            emit(e)

    manifest = {
        "schema": MANIFEST_SCHEMA, "run_id": run_id, "created": datetime.now(timezone.utc).isoformat(),
        "profile": profile, "pipeline": pipeline.pipeline, "title": pipeline.stage("arrange").params.get("title"),
        "params": pipeline.params,
        "options": {"reuse": str(reuse) if reuse else None, "allow_heavy": allow_heavy, "cold": sorted(cold or [])},
        "input": {"path": str(audio), "sha256": cache.hashes.file(audio), "bytes": audio.stat().st_size},
        "git": git_state(), "host": host_info(), "status": "running", "stages": [], "outputs": {},
    }
    if previous_run_id:
        manifest["previous_run_id"] = previous_run_id
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    on_event({"type": "job", "status": "running", "profile": profile, "stages": [s.name for s in pipeline.stages]})
    ex = Executor(cache, adapters, on_event, reuse_dir=reuse, allow_heavy=allow_heavy, cold=cold, cancel=cancel)
    t0 = time.time()
    results = {}
    try:
        results = ex.run(pipeline, audio, run_dir)
        manifest["status"] = "succeeded"
    except Cancelled:
        manifest["status"] = "cancelled"
    except StageFailed as e:
        manifest["status"] = "failed"
        manifest["error"] = str(e)
    except Exception as e:  # noqa: BLE001 - recorded in the manifest, the job fails
        manifest["status"] = "failed"
        manifest["error"] = f"{type(e).__name__}: {e}"
    finally:
        partial = getattr(ex, "results", None) or {}
        manifest["stages"] = [r.record() for r in partial.values()]
        if manifest["status"] == "succeeded":
            outputs_dir = run_dir / "outputs"
            outputs_dir.mkdir(exist_ok=True)
            for name, (stage, f) in pipeline.outputs.items():
                r = results.get(stage)
                if r and f in r.files:
                    link_or_clone(r.out_dir / f, outputs_dir / name)
                    manifest["outputs"][name] = r.files[f]
                    if out is not None:
                        link_or_clone(r.out_dir / f, Path(out) / name)
            if out is not None:
                manifest["out"] = str(Path(out).resolve())
        manifest["finished"] = datetime.now(timezone.utc).isoformat()
        manifest["seconds"] = round(time.time() - t0, 3)
        manifest["devices"] = sorted({r.adapter["device"] for r in partial.values() if r.adapter})
        cache.hashes.save()
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
        if out is not None and manifest["status"] == "succeeded":
            (Path(out) / "manifest.json").write_text(json.dumps(manifest, indent=1))
        on_event({"type": "job", "status": manifest["status"], "error": manifest.get("error")})
        events_file.close()
    return manifest


def rerun(settings: Settings, manifest_path: Path, **overrides) -> tuple[dict, dict]:
    """Re-run a manifest's job (same input, profile, title, params); returns (old, new) manifests."""
    old = json.loads(Path(manifest_path).read_text())
    audio = Path(old["input"]["path"])
    cache, _ = _session(settings)
    if not audio.exists() or cache.hashes.file(audio) != old["input"]["sha256"]:
        raise RunRefused(f"input {audio} is missing or changed since the manifest was written")
    opts = old.get("options", {})
    kwargs = {"title": old.get("title"), "params": old.get("params"),
              "reuse": Path(opts["reuse"]) if opts.get("reuse") else None,
              "allow_heavy": opts.get("allow_heavy", True), **overrides}
    new = run(settings, audio, old["profile"], **kwargs)
    return old, new


def diff_manifests(old: dict, new: dict) -> dict:
    """Outputs and stage outputs that differ between two runs."""
    outs = {k: (old["outputs"].get(k), new["outputs"].get(k)) for k in set(old["outputs"]) | set(new["outputs"])}
    so = {s["stage"]: s.get("outputs_digest") for s in old["stages"]}
    sn = {s["stage"]: s.get("outputs_digest") for s in new["stages"]}
    renders = (".pdf", ".mp3", ".mid")  # MuseScore renders carry timestamps; reported, not gated
    return {"outputs_identical": sorted(k for k, (a, b) in outs.items() if a == b and a),
            "outputs_different": sorted(k for k, (a, b) in outs.items() if a != b and not k.endswith(renders)),
            "renders_different": sorted(k for k, (a, b) in outs.items() if a != b and k.endswith(renders)),
            "stages_different": sorted(k for k in set(so) | set(sn) if so.get(k) != sn.get(k))}
