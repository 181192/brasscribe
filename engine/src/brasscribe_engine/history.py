"""Benchmark history and read-only report directories.

Every gated suite run is stored as JSON under <data>/bench/history/, so Studio
can show trends. Conversion-parity and core-conformance reports are JSON files
other tools write into their own directories; the engine only lists and serves them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .adapters import host_device
from .config import Settings


def save(settings: Settings, report: dict, target: str, mode: str) -> dict:
    from .runner import git_state

    d = settings.bench_history_dir
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    run = {"id": now.strftime("%Y%m%dT%H%M%S%fZ"), "created": now.isoformat(), "target": target, "mode": mode,
           "passed": report["passed"], "git_sha": git_state().get("sha"), "device": host_device(),
           "suites": report["suites"]}
    (d / f"{run['id']}.json").write_text(json.dumps(run, indent=1))
    return run


def entries(settings: Settings, suite: str | None = None, limit: int = 1000) -> list[dict]:
    """One row per suite result, newest first."""
    d = settings.bench_history_dir
    rows: list[dict] = []
    for p in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        run = json.loads(p.read_text())
        t = datetime.fromisoformat(run["created"]).timestamp()
        for s in run["suites"]:
            if suite and s["suite"] != suite:
                continue
            rows.append({"time": t, "run_id": run["id"], "target": run["target"], "suite": s["suite"],
                         "status": s["status"], "reason": s.get("reason"), "metrics": s.get("metrics", {}),
                         "checks": s.get("checks", []), "manifest": str(p), "git_sha": run.get("git_sha"),
                         "device": run.get("device")})
            if len(rows) >= limit:
                return rows
    return rows


def reports(root: Path) -> list[dict]:
    """Every *.json report under root (recursively), as stored, with its file name added as `_file`."""
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*.json")):
        try:
            data = json.loads(p.read_text())
        except ValueError:
            continue
        out.append({**data, "_file": p.relative_to(root).as_posix()} if isinstance(data, dict)
                   else {"_file": p.relative_to(root).as_posix(), "data": data})
    return out
