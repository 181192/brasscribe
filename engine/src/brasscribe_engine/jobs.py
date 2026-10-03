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
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
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
        # A renamed run's PDF, MIDI and braille are made again here, one at a time, away from the request.
        self.render_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="brasscribe-render")
        self.renders: dict[str, Future] = {}  # the last render queued per run (for tests)
        self._rename_lock = threading.Lock()  # a rename's writes and a render's swap never interleave
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
        self.render_pool.shutdown(wait=True, cancel_futures=True)

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
        self.renders.pop(job_id, None)  # a render still queued finds the run gone and makes nothing
        return "deleted"

    def rename(self, job_id: str, title: str) -> str:
        """Retitle a finished run: its manifest, Composition, the score's and parts' MusicXML, the talking
        score, and a tab's text and playing instructions. The PDFs, MIDI and braille it has are then made
        again with the new title in the background (render_again); the audio has no title.
        Returns "renamed", "unknown" or "active"."""
        if not valid_id(job_id):
            return "unknown"
        job = self.get(job_id)
        if job is None:
            return "unknown"
        if job.status not in TERMINAL:
            return "active"
        with self._rename_lock:
            self._retitle(job, title)
        if _rendered(self.run_dir(job_id) / "outputs"):
            self.renders[job_id] = self.render_pool.submit(self.render_again, job_id, title)
        return "renamed"

    def _retitle(self, job: Job, title: str) -> None:
        job_id = job.id
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
        tab = out / "tab.musicxml"
        if tab.exists():  # its header holds the title cut to the page's width, as when it was written
            from . import bass_tab

            _write(tab, _retitle_musicxml(tab.read_text(), bass_tab.page_title(title)))
            # The text exports start with the same title: tab.txt on its first line, the instructions with an
            # empty line after it.
            for name in bass_tab.TEXT_OUTPUTS:
                if (out / name).exists():
                    text = (out / name).read_text(encoding="utf-8")
                    gap = "" if name == bass_tab.TEXT_TAB else "\n"
                    _write(out / name, bass_tab.retitled_text(text, job.title or "", title, gap), encoding="utf-8")
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

    def render_again(self, job_id: str, title: str) -> list[str]:
        """Make a renamed run's rendered files again from its retitled MusicXML: the score's PDF and MIDI and
        the parts' PDFs through MuseScore (when it is installed), the braille without it. Only files the run
        has are made, in a directory of their own, and they replace the old ones only if the run still has
        this title (a later rename renders its own). Returns the files replaced."""
        out = self.run_dir(job_id) / "outputs"
        try:
            with tempfile.TemporaryDirectory(prefix="brasscribe-render-") as tmp:
                made = _render(out, Path(tmp))
                with self._rename_lock:
                    job = self.get(job_id)
                    if job is None or job.title != title or not out.is_dir():
                        return []
                    for name in made:
                        _replace(Path(tmp) / name, out / name)
                return made
        except Exception:  # noqa: BLE001 - the run keeps its old renders; a rename never fails on this
            return []

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


# What MuseScore renders from a run's MusicXML (the export stages): the band score, its parts and a tab.
RENDERED = {"brass-band.musicxml": ("brass-band.pdf", "brass-band.mid"), "tab.musicxml": ("tab.pdf", "tab.mid")}


def _rendered(out: Path) -> bool:
    """Whether the run has a rendered file that holds its title."""
    return (any((out / name).exists() for names in RENDERED.values() for name in names)
            or (out / "brass-band.brf").exists() or any((out / "parts").glob("*.pdf")) or any((out / "parts").glob("*.brf")))


def _render(out: Path, into: Path) -> list[str]:
    """The rendered files `out` has, made again from its MusicXML into `into` (same names). PDF and MIDI as the
    export stages make them; none without MuseScore. Braille for the score and the parts that have it."""
    from brasscribe_music import musescore

    from . import braille
    from .stages import PART_STYLE

    made: list[str] = []
    if musescore.binary():
        for src, names in RENDERED.items():
            names = [n for n in names if (out / n).exists()]
            if (out / src).exists() and names:
                if musescore.convert_many([(out / src, [into / n for n in names])]):
                    raise RuntimeError(f"MuseScore did not render {src}")
                made += names
        parts = [p for p in sorted((out / "parts").glob("*.musicxml")) if p.with_suffix(".pdf").exists()]
        if parts:
            if musescore.convert_many([(p, into / "parts" / p.with_suffix(".pdf").name) for p in parts],
                                      style=PART_STYLE if PART_STYLE.exists() else None):
                raise RuntimeError("MuseScore did not render every part")
            made += [f"parts/{p.with_suffix('.pdf').name}" for p in parts]
    for src in [out / "brass-band.musicxml", *sorted((out / "parts").glob("*.musicxml"))]:
        brf = src.with_suffix(".brf")
        if src.exists() and brf.exists():
            try:
                text = braille.translate(src).brf
            except Exception:  # noqa: BLE001 - as in the export stage: that file keeps its old braille
                continue
            rel = brf.relative_to(out).as_posix()
            (into / rel).parent.mkdir(parents=True, exist_ok=True)
            (into / rel).write_bytes(text.encode("ascii"))
            made.append(rel)
    return made


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

    # XML has no way to write a control character: a title that holds one would make the file unreadable.
    title = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", re.sub(r"[\t\n\r]+", " ", title))
    tag = re.compile(r"(<work-title>)[\s\S]*?(</work-title>)")
    work = f"<work><work-title>{escape(title)}</work-title></work>"
    if tag.search(text):
        return tag.sub(lambda mt: mt.group(1) + escape(title) + mt.group(2), text, count=1)
    if re.search(r"<score-partwise\b[^>]*/>", text):
        return re.sub(r"<score-partwise\b([^>]*)/>", lambda mt: f"<score-partwise{mt.group(1)}>{work}</score-partwise>",
                      text, count=1)
    return re.sub(r"(<score-partwise\b[^>]*>)", lambda mt: mt.group(1) + work, text, count=1)


def _replace(src: Path, dst: Path) -> None:
    """Replace `dst` with a copy of `src` (from another file system), as _write does."""
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    try:
        os.replace(tmp, dst)
    except PermissionError:
        os.chmod(dst, dst.stat().st_mode | stat.S_IWUSR)
        os.replace(tmp, dst)


def _write(path: Path, text: str, encoding: str | None = None) -> None:
    """Replace `path` with `text`. Outputs are read-only hardlinks into the artifact cache: replacing the name
    leaves the cache's copy as it was, but Windows refuses to replace a read-only file, so there the flag is
    cleared first. The flag belongs to the file, not the name, so the cache's copy loses it too (its content
    is unchanged, and the cache checks content by hash)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.chmod(path, path.stat().st_mode | stat.S_IWUSR)
        os.replace(tmp, path)
