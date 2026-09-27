"""Job queue for the HTTP service: runs jobs on a worker thread and fans out progress events.

Jobs run one at a time (heavy stages also take the machine-wide GPU mutex).
Events are kept per job with monotonic ids so a client can resume a stream
with Last-Event-ID. Finished runs from earlier server sessions are listed from
their manifests in the runs directory.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import profiles, runner
from .config import Settings

TERMINAL = {"succeeded", "failed", "cancelled"}


@dataclass
class Job:
    id: str
    profile: str
    title: str | None
    audio_id: str | None
    audio_path: Path
    params: dict
    allow_heavy: bool = True
    cold: set[str] = field(default_factory=set)
    previous_run_id: str | None = None
    status: str = "queued"
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    stages: dict[str, dict] = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)
    cond: threading.Condition = field(default_factory=threading.Condition)

    def add_event(self, e: dict) -> None:
        with self.cond:
            if "id" not in e:
                e = {"id": (self.events[-1]["id"] + 1) if self.events else 0, "run": self.id, "time": time.time(), **e}
            self.events.append(e)
            if e.get("type") == "stage":
                st = self.stages.setdefault(e["stage"], {"name": e["stage"], "kind": e.get("kind"), "status": "pending"})
                st["status"] = e["status"]
                for k in ("seconds", "device"):
                    if k in e:
                        st[k] = e[k]
            elif e.get("type") == "job" and e.get("status") in TERMINAL:
                self.status = e["status"]
                self.error = e.get("error")
                self.finished = time.time()
            self.cond.notify_all()

    def events_after(self, after: int, timeout: float) -> list[dict]:
        with self.cond:
            if not any(e["id"] > after for e in self.events) and self.status not in TERMINAL:
                self.cond.wait(timeout)
            return [e for e in self.events if e["id"] > after]


class JobManager:
    def __init__(self, settings: Settings, workers: int = 1):
        self.settings = settings.ensure()
        self.jobs: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="brasscribe-job")
        self.lock = threading.Lock()

    def submit(self, audio: Path, profile: str, *, audio_id: str | None = None, title: str | None = None,
               params: dict | None = None, allow_heavy: bool = True, cold: set[str] | None = None,
               previous_run_id: str | None = None) -> Job:
        pipeline = profiles.build(profile, audio, title, params)
        job = Job(runner.new_run_id(profile), profile, pipeline.stage("arrange").params.get("title"), audio_id,
                  Path(audio), dict(params or {}), allow_heavy, set(cold or ()), previous_run_id)
        for s in pipeline.stages:
            job.stages[s.name] = {"name": s.name, "kind": s.kind, "status": "pending"}
        with self.lock:
            self.jobs[job.id] = job
        job.add_event({"type": "job", "status": "queued"})
        self.pool.submit(self._run, job)
        return job

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            job.add_event({"type": "job", "status": "cancelled"})
            return
        job.status, job.started = "running", time.time()
        try:
            runner.run(self.settings, job.audio_path, job.profile, title=job.title, params=job.params,
                       allow_heavy=job.allow_heavy, cold=job.cold, run_id=job.id, emit=job.add_event,
                       cancel=job.cancel, previous_run_id=job.previous_run_id)
        except Exception as e:  # noqa: BLE001 - reported as a failed job
            job.add_event({"type": "job", "status": "failed", "error": f"{type(e).__name__}: {e}"})

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            job = self.jobs.get(job_id)
        return job or self._from_disk(job_id)

    def list(self) -> list[Job]:
        with self.lock:
            live = dict(self.jobs)
        for d in sorted(self.settings.runs_dir.glob("*/manifest.json")):
            if d.parent.name not in live:
                j = self._from_disk(d.parent.name)
                if j:
                    live[j.id] = j
        return sorted(live.values(), key=lambda j: j.created, reverse=True)

    def counts(self) -> tuple[int, int]:
        """(running, queued) among the jobs this engine process runs; a cancelled queued job is not counted."""
        with self.lock:
            live = list(self.jobs.values())
        running = sum(j.status == "running" for j in live)
        queued = sum(j.status == "queued" and not j.cancel.is_set() for j in live)
        return running, queued

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job and job.status not in TERMINAL:
            job.cancel.set()
        return job

    def delete(self, job_id: str) -> str:
        """Remove a finished run's directory and forget the job; the artifact cache is untouched.

        Returns "deleted", "unknown" or "active" (queued or running: not deleted)."""
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            return "unknown"
        job = self.get(job_id)
        if job is None:
            return "unknown"
        if job.status not in TERMINAL:
            return "active"
        root = self.settings.runs_dir.resolve()
        d = self.run_dir(job_id).resolve()
        if d.parent != root:
            return "unknown"
        if d.is_dir():
            def writable_retry(func, path, _exc):  # Windows refuses to unlink read-only files
                os.chmod(path, stat.S_IWRITE)
                func(path)

            shutil.rmtree(d, onerror=writable_retry)
        with self.lock:
            self.jobs.pop(job_id, None)
        return "deleted"

    def rename(self, job_id: str, title: str) -> str:
        """Retitle a finished run in its manifest, Composition and MusicXML. Returns "renamed", "unknown" or "active"."""
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            return "unknown"
        job = self.get(job_id)
        if job is None:
            return "unknown"
        if job.status not in TERMINAL:
            return "active"
        from xml.sax.saxutils import escape

        d = self.run_dir(job_id)
        mpath = d / "manifest.json"
        if mpath.exists():
            m = json.loads(mpath.read_text())
            m["title"] = title
            _write(mpath, json.dumps(m, indent=2))
        comp = d / "outputs" / "composition.json"
        if comp.exists():
            c = json.loads(comp.read_text())
            c["title"] = title
            _write(comp, json.dumps(c))
        xml = d / "outputs" / "brass-band.musicxml"
        if xml.exists():
            import re

            text = xml.read_text()
            tag = re.compile(r"(<work-title>)[\s\S]*?(</work-title>)")
            work = f"<work><work-title>{escape(title)}</work-title></work>"
            if tag.search(text):
                text = tag.sub(lambda mt: mt.group(1) + escape(title) + mt.group(2), text, count=1)
            elif re.search(r"<score-partwise\b[^>]*/>", text):
                text = re.sub(r"<score-partwise\b([^>]*)/>", lambda mt: f"<score-partwise{mt.group(1)}>{work}</score-partwise>",
                              text, count=1)
            else:
                text = re.sub(r"(<score-partwise\b[^>]*>)", lambda mt: mt.group(1) + work, text, count=1)
            _write(xml, text)
        job.title = title
        return "renamed"

    def run_dir(self, job_id: str) -> Path:
        return self.settings.runs_dir / job_id

    def _from_disk(self, job_id: str) -> Job | None:
        mpath = self.run_dir(job_id) / "manifest.json"
        if "/" in job_id or ".." in job_id or not mpath.exists():
            return None
        m = json.loads(mpath.read_text())
        job = Job(m["run_id"], m["profile"], m.get("title"), None, Path(m["input"]["path"]), m.get("params", {}),
                  m.get("options", {}).get("allow_heavy", True), set(m.get("options", {}).get("cold", [])),
                  m.get("previous_run_id"), status=m.get("status", "unknown"),
                  created=mpath.stat().st_ctime, error=m.get("error"))
        for st in m.get("stages", []):
            job.stages[st["stage"]] = {"name": st["stage"], "kind": st["kind"], "status": st["status"],
                                       "seconds": st.get("seconds"), "device": (st.get("adapter") or {}).get("device")}
        ev = self.run_dir(job_id) / "events.jsonl"
        if ev.exists():
            job.events = [json.loads(line) for line in ev.read_text().splitlines() if line.strip()]
        if job.status == "running":  # the server that ran it is gone
            job.status = "failed"
            job.error = job.error or "interrupted"
        return job


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
