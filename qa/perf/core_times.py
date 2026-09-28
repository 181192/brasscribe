"""Wall time and peak memory of the Rust CLI on each conformance case, without the Python reference.

    cd core && cargo build --release -p brasscribe-cli && cd ..
    PYTHONPATH=core/conformance pixi run python qa/perf/core_times.py core/target/release/brasscribe-core [mikkel]

Uses the conformance suite's own case list and command lines (brasscribe_conformance.run.rust_cmd),
writes into a temporary directory, and reports the best of three runs and the peak resident set
(/usr/bin/time -l on macOS, -v on Linux). Cases whose inputs the full suite synthesises first
(solo-beats layers) exit with 101 here; run the suite once to create them.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from brasscribe_conformance.cases import all_cases
from brasscribe_conformance.run import rust_cmd

binary = Path(sys.argv[1])
only = sys.argv[2] if len(sys.argv) > 2 else None
timer = ["/usr/bin/time", "-l"] if sys.platform == "darwin" else ["/usr/bin/time", "-v"]
work = Path(tempfile.mkdtemp(prefix="core-times-"))
total = 0.0
for case in all_cases(work, only):
    out = work / case.id / "rust"
    out.mkdir(parents=True, exist_ok=True)
    best, peak, rc = float("inf"), 0, 0
    for _ in range(3):
        t0 = time.perf_counter()
        p = subprocess.run([*timer, *rust_cmd(binary, case, out)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        best = min(best, time.perf_counter() - t0)
        rc = p.returncode
        mac = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
        linux = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.stderr)
        peak = max(peak, int(mac.group(1)) if mac else int(linux.group(1)) * 1024 if linux else 0)
    total += best
    print(f"{case.id:60s} {case.kind:7s} rc={rc:<3d} {best * 1000:7.0f} ms  peak {peak / 1e6:6.0f} MB", flush=True)
print(f"total (best of three each): {total:.1f} s; outputs in {work}")
