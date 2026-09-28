"""Per-stage timings over every run manifest in a runs directory.

    pixi run python qa/perf/run_stages.py [data/runs]

Prints, per (stage, status), how many runs and the median and largest seconds, then the
runs in which some stage actually ran (not cached or imported). A stage's seconds include
any wait for the GPU mutex (adapters.py), so an outlier on a short input is usually queueing.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/runs")
per: dict[tuple[str, str], list[float]] = defaultdict(list)
ran = []
for mf in sorted(root.glob("*/manifest.json")):
    try:
        m = json.loads(mf.read_text())
    except (OSError, ValueError):
        continue
    stages = m.get("stages", [])
    for s in stages:
        per[(s["stage"], s["status"])].append(s.get("seconds") or 0.0)
    if any(s["status"] == "ran" for s in stages):
        total = sum(s.get("seconds") or 0.0 for s in stages)
        worst = max(stages, key=lambda s: s.get("seconds") or 0.0)
        ran.append((mf.parent.name, m.get("status"), total, worst["stage"], worst.get("seconds") or 0.0,
                    (m.get("input") or {}).get("bytes")))

print(f"{len(list(root.glob('*/manifest.json')))} manifests under {root}\n")
print(f"{'stage':36s} {'status':9s} {'n':>4s} {'median s':>9s} {'max s':>8s}")
for (stage, status), v in sorted(per.items()):
    print(f"{stage:36s} {status:9s} {len(v):4d} {statistics.median(v):9.2f} {max(v):8.2f}")
print(f"\n{'run':48s} {'status':9s} {'total s':>8s}  slowest stage")
for run, status, total, stage, secs, size in ran:
    print(f"{run:48s} {status or '-':9s} {total:8.1f}  {stage} {secs:.1f} s (input {size or 0:,} B)")
