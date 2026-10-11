"""Runs the Rust-core conformance suite (core/conformance) in the background for Studio's "Run conformance".

One run at a time: `uv run --project core/conformance python -m scribe_conformance.run --work <dir>`,
without --musescore (no MuseScore launches). Output goes to <dir>/run.log; the suite itself writes
<dir>/report.json, which listConformanceReports serves.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import REPO_ROOT, child_env

PROJECT = REPO_ROOT / "core" / "conformance"
LOG_TAIL_LINES = 40


@dataclass
class RunState:
    status: str = "idle"  # idle | running | succeeded | failed
    started: float | None = None
    finished: float | None = None
    exit_code: int | None = None
    command: list[str] = field(default_factory=list)
    log: str | None = None


class ConformanceRunner:
    def __init__(self, work: Path, project: Path = PROJECT):
        self.work, self.project = Path(work), Path(project)
        self.state = RunState()
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return (self.project / "scribe_conformance" / "run.py").exists()

    def command(self) -> list[str]:
        return ["uv", "run", "--project", str(self.project), "python", "-m", "scribe_conformance.run",
                "--work", str(self.work)]

    def start(self) -> bool:
        """Start a run; False when one is already running."""
        with self._lock:
            if self.state.status == "running":
                return False
            self.work.mkdir(parents=True, exist_ok=True)
            log = self.work / "run.log"
            self.state = RunState("running", time.time(), command=self.command(), log=str(log))
        threading.Thread(target=self._run, args=(log,), daemon=True, name="scribe-conformance").start()
        return True

    def _run(self, log: Path) -> None:
        try:
            with log.open("w") as f:
                code = subprocess.run(self.state.command, cwd=self.project, stdin=subprocess.DEVNULL, stdout=f,
                                      stderr=subprocess.STDOUT, env=child_env()).returncode
        except OSError as e:
            log.write_text(f"could not start: {e}\n")
            code = -1
        with self._lock:
            self.state.exit_code = code
            self.state.finished = time.time()
            self.state.status = "succeeded" if code == 0 else "failed"

    def snapshot(self) -> dict:
        with self._lock:
            d = asdict(self.state)
        tail = None
        if d["log"] and Path(d["log"]).exists():
            tail = "\n".join(Path(d["log"]).read_text(errors="replace").splitlines()[-LOG_TAIL_LINES:])
        return {**d, "log_tail": tail, "available": self.available}
