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
from datetime import datetime
from pathlib import Path

from . import profiles, runner
from .names import valid_id
from .config import Settings

TERMINAL = {"succeeded", "failed", "cancelled"}
# Finished jobs stay in memory, events and all, for this long and at most this many; after that they are read
# back from their run directory when asked for. (A job that failed before it had one is then forgotten.)
KEEP_FINISHED_S = 600.0
KEEP_FINISHED = 50


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
    device_name: str | None = None
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
                for k in ("seconds", "queue_wait_s", "run_s", "device"):
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
        # Finished runs from disk for list(), keyed by the manifest's (mtime_ns, size): a list parses only
        # manifests that changed since the last one, and never reads events.jsonl.
        self._summaries: dict[str, tuple[tuple[int, int], Job, list[str]]] = {}
        self._summaries_lock = threading.Lock()
        self.manifest_parses = 0  # for tests: manifests parsed by list()

    def submit(self, audio: Path, profile: str, *, audio_id: str | None = None, title: str | None = None,
               params: dict | None = None, allow_heavy: bool = True, cold: set[str] | None = None,
               previous_run_id: str | None = None, device_name: str | None = None) -> Job:
        pipeline = profiles.build(profile, audio, title, params)
        job = Job(runner.new_run_id(profile), profile, pipeline.stage("arrange").params.get("title"), audio_id,
                  Path(audio), dict(params or {}), allow_heavy, set(cold or ()), previous_run_id,
                  device_name)
        for s in pipeline.stages:
            job.stages[s.name] = {"name": s.name, "kind": s.kind, "status": "pending"}
        self._evict()
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
                       cancel=job.cancel, previous_run_id=job.previous_run_id, audio_id=job.audio_id,
                       device_name=job.device_name)
        except Exception as e:  # noqa: BLE001 - reported as a failed job
            job.add_event({"type": "job", "status": "failed", "error": f"{type(e).__name__}: {e}"})

    def _evict(self) -> None:
        """Forget finished jobs past KEEP_FINISHED_S or KEEP_FINISHED; an open event stream keeps its own."""
        now = time.time()
        with self.lock:
            done = sorted((j for j in self.jobs.values() if j.status in TERMINAL and j.finished is not None),
                          key=lambda j: j.finished, reverse=True)
            for i, j in enumerate(done):
                if i >= KEEP_FINISHED or now - j.finished > KEEP_FINISHED_S:
                    del self.jobs[j.id]

    def get(self, job_id: str) -> Job | None:
        if not valid_id(job_id):
            return None
        with self.lock:
            job = self.jobs.get(job_id)
        return job or self._from_disk(job_id)

    def list(self) -> list[Job]:
        self._evict()
        with self.lock:
            live = dict(self.jobs)
        seen: set[str] = set()
        try:
            entries = list(os.scandir(self.settings.runs_dir))
        except FileNotFoundError:
            entries = []
        for d in entries:
            if d.name in live or not valid_id(d.name) or not d.is_dir():
                continue
            j = self._summary(d.name)
            if j:
                seen.add(d.name)
                live[j.id] = j
        with self._summaries_lock:
            for gone in set(self._summaries) - seen:
                del self._summaries[gone]
        return sorted(live.values(), key=lambda j: j.created, reverse=True)

    def _summary(self, job_id: str) -> Job | None:
        """A finished run from disk without its events, reparsed only when manifest.json changed."""
        mpath = self.run_dir(job_id) / "manifest.json"
        try:
            st = mpath.stat()
        except FileNotFoundError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        with self._summaries_lock:
            hit = self._summaries.get(job_id)
        if hit and hit[0] == key:
            return hit[1]
        try:
            job = self._from_disk(job_id, events=False)
        except (OSError, ValueError, KeyError):
            return None
        if job is None:
            return None
        with self._summaries_lock:
            self.manifest_parses += 1
            self._summaries[job_id] = (key, job, _list_outputs(self.run_dir(job_id) / "outputs"))
        return job

    def outputs(self, job: Job) -> list[str]:
        """Files under the run's outputs/ (relative, sorted); cached with the summary for runs listed from disk."""
        with self._summaries_lock:
            hit = self._summaries.get(job.id)
        if hit and hit[1] is job:
            return hit[2]
        return _list_outputs(self.run_dir(job.id) / "outputs")

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

    def shutdown(self) -> None:
        """Cancel every queued and running job (a running model is stopped) and wait for the worker to end."""
        with self.lock:
            live = [j for j in self.jobs.values() if j.status not in TERMINAL]
        for job in live:
            job.cancel.set()
        self.pool.shutdown(wait=True)

    def delete(self, job_id: str) -> str:
        """Remove a finished run's directory and forget the job; the artifact cache is untouched.

        Returns "deleted", "unknown" or "active" (queued or running: not deleted)."""
        if not valid_id(job_id):
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
        """Retitle a finished run: its manifest, Composition, the score's and parts' MusicXML and the talking
        score. Rendered files (PDF, braille, MIDI, audio) keep the title they were made with.
        Returns "renamed", "unknown" or "active"."""
        if not valid_id(job_id):
            return "unknown"
        job = self.get(job_id)
        if job is None:
            return "unknown"
        if job.status not in TERMINAL:
            return "active"
        d = self.run_dir(job_id)
        out = d / "outputs"
        mpath = d / "manifest.json"
        if mpath.exists():
            m = json.loads(mpath.read_text())
            m["title"] = title
            _write(mpath, json.dumps(m, indent=2))
        comp = out / "composition.json"
        if comp.exists():
            c = json.loads(comp.read_text())
            c["title"] = title
            _write(comp, json.dumps(c))
        for xml in [out / "brass-band.musicxml", *sorted((out / "parts").glob("*.musicxml"))]:
            if xml.exists():
                _write(xml, _retitle_musicxml(xml.read_text(), title))
        talking = out / "talking-score.json"
        if talking.exists():
            from . import talking_score

            doc = json.loads(talking.read_text())
            doc["title"] = title
            _write(talking, json.dumps(doc, ensure_ascii=False, indent=1))
            en = talking_score.Settings()  # as the export stage writes them
            for name, render in (("talking-score.html", talking_score.to_html), ("talking-score.txt", talking_score.to_text)):
                if (out / name).exists():
                    _write(out / name, render(doc, en))
        job.title = title
        return "renamed"

    def run_dir(self, job_id: str) -> Path:
        return self.settings.runs_dir / job_id

    def _from_disk(self, job_id: str, *, events: bool = True) -> Job | None:
        if not valid_id(job_id):
            return None
        mpath = self.run_dir(job_id) / "manifest.json"
        if not mpath.exists():
            return None
        m = json.loads(mpath.read_text())
        try:  # renaming or finishing a run rewrites its manifest, so the file's own times say nothing
            created = datetime.fromisoformat(m["created"]).timestamp()
        except (KeyError, TypeError, ValueError):  # manifests before the field
            created = mpath.stat().st_ctime
        job = Job(m["run_id"], m["profile"], m.get("title"), m.get("audio_id"), Path(m["input"]["path"]),
                  m.get("params", {}), m.get("options", {}).get("allow_heavy", True),
                  set(m.get("options", {}).get("cold", [])), m.get("previous_run_id"), m.get("device_name"),
                  status=m.get("status", "unknown"),
                  created=created, error=m.get("error"))
        for st in m.get("stages", []):
            job.stages[st["stage"]] = {"name": st["stage"], "kind": st["kind"], "status": st["status"],
                                       "seconds": st.get("seconds"), "queue_wait_s": st.get("queue_wait_s"),
                                       "run_s": st.get("run_s"), "device": (st.get("adapter") or {}).get("device")}
        ev = self.run_dir(job_id) / "events.jsonl"
        if events and ev.exists():
            job.events = [json.loads(line) for line in ev.read_text().splitlines() if line.strip()]
        if job.status == "running":  # the server that ran it is gone
            job.status = "failed"
            job.error = job.error or "interrupted"
        return job


def _list_outputs(d: Path) -> list[str]:
    out: list[str] = []
    for root, _dirs, files in os.walk(d):
        rel = os.path.relpath(root, d)
        prefix = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        out.extend(prefix + f for f in files)
    return sorted(out)


def _retitle_musicxml(text: str, title: str) -> str:
    """MusicXML with its work title set to `title` (added when the score has none)."""
    import re
    from xml.sax.saxutils import escape

    tag = re.compile(r"(<work-title>)[\s\S]*?(</work-title>)")
    work = f"<work><work-title>{escape(title)}</work-title></work>"
    if tag.search(text):
        return tag.sub(lambda mt: mt.group(1) + escape(title) + mt.group(2), text, count=1)
    if re.search(r"<score-partwise\b[^>]*/>", text):
        return re.sub(r"<score-partwise\b([^>]*)/>", lambda mt: f"<score-partwise{mt.group(1)}>{work}</score-partwise>",
                      text, count=1)
    return re.sub(r"(<score-partwise\b[^>]*>)", lambda mt: mt.group(1) + work, text, count=1)


def _write(path: Path, text: str) -> None:
    """Replace `path` with `text`. Outputs are read-only hardlinks into the artifact cache: replacing the name
    leaves the cache's copy as it was, but Windows refuses to replace a read-only file, so there the flag is
    cleared first. The flag belongs to the file, not the name, so the cache's copy loses it too (its content
    is unchanged, and the cache checks content by hash)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.chmod(path, path.stat().st_mode | stat.S_IWUSR)
        os.replace(tmp, path)
