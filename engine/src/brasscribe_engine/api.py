"""HTTP service: Studio (browser, same machine) and companion mode for the native Play apps.

Clients on the loopback interface are trusted. Any other client pairs once:
the engine prints a pairing code at start, `POST /v1/pair` with that code
returns the shared bearer token, and every other request carries
`Authorization: Bearer <token>`.

Progress is streamed as Server-Sent Events with monotonic ids; reconnect with
`Last-Event-ID` (or `?after=`) to resume. A comment line is sent every 15 s
while nothing happens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, history, inspection, profiles
from . import schemas as m
from .adapters import host_device
from .config import Settings
from .jobs import TERMINAL, Job, JobManager

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
STATIC = Path(__file__).resolve().parent / "static"
HEARTBEAT_S = 15.0

MEDIA = {
    "composition.json": "application/json",
    "brass-band.musicxml": "application/vnd.recordare.musicxml+xml",
    "brass-band.pdf": "application/pdf",
    "brass-band.mid": "audio/midi",
    "brass-band.mp3": "audio/mpeg",
    "manifest.json": "application/json",
}
SUFFIX_MEDIA = {".json": "application/json", ".musicxml": MEDIA["brass-band.musicxml"], ".pdf": "application/pdf",
                ".mid": "audio/midi", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
                ".beats": "text/plain"}


def media_type(name: str) -> str:
    return MEDIA.get(name) or SUFFIX_MEDIA.get(Path(name).suffix, "application/octet-stream")


@dataclass
class Pairing:
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    code: str = field(default_factory=lambda: f"{secrets.randbelow(10**6):06d}")
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def pair(self, code: str) -> str | None:
        with self.lock:
            if hmac.compare_digest(code.strip(), self.code):
                return self.token
            self.failures += 1
            if self.failures >= 5:  # rotate after repeated wrong guesses
                self.code, self.failures = f"{secrets.randbelow(10**6):06d}", 0
            return None


def create_app(settings: Settings | None = None, *, trust_loopback: bool = True, workers: int = 1) -> FastAPI:
    settings = (settings or Settings()).ensure()
    app = FastAPI(
        title="brasscribe engine",
        version=__version__,
        description="Recording in, brass-band score out. Jobs run a profile's stage DAG with a content-addressed "
                    "cache; progress streams as Server-Sent Events. Loopback clients are trusted; LAN clients pair "
                    "with the code the engine prints and then send a bearer token.",
    )
    app.state.settings = settings
    app.state.jobs = JobManager(settings, workers=workers)
    app.state.pairing = Pairing(token=settings.token) if settings.token else Pairing()
    app.state.trust_loopback = trust_loopback

    def is_trusted(request: Request) -> bool:
        host = request.client.host if request.client else ""
        return app.state.trust_loopback and host in LOOPBACK | {"testclient"}

    def auth(request: Request, authorization: str | None = Header(None)) -> None:
        if is_trusted(request):
            return
        token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
        if not token or not hmac.compare_digest(token, app.state.pairing.token):
            raise HTTPException(401, "pair first: POST /v1/pair with the engine's pairing code", {"WWW-Authenticate": "Bearer"})

    jobs: JobManager = app.state.jobs

    def job_or_404(job_id: str) -> Job:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"no job {job_id}")
        return job

    def outputs_of(job: Job) -> list[str]:
        d = jobs.run_dir(job.id) / "outputs"
        return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()) if d.is_dir() else []

    def job_model(job: Job) -> m.Job:
        stages = list(job.stages.values())
        done = sum(s["status"] in ("cached", "imported", "ran", "skipped") for s in stages)
        return m.Job(id=job.id, profile=job.profile, title=job.title, audio_id=job.audio_id, status=job.status,
                     created=job.created, started=job.started, finished=job.finished, error=job.error,
                     progress=round(done / len(stages), 4) if stages else 0.0, previous_run_id=job.previous_run_id,
                     stages=[m.StageState(**s) for s in stages], outputs=outputs_of(job))

    def output_file(job_id: str, name: str) -> FileResponse:
        job = job_or_404(job_id)
        root = jobs.run_dir(job.id) if name == "manifest.json" else jobs.run_dir(job.id) / "outputs"
        p = (root / name).resolve()
        if not inspection.inside(root, p) or not p.is_file():
            raise HTTPException(404, f"{name} not available for job {job_id} (status {job.status})")
        return FileResponse(p, media_type=media_type(name), filename=p.name)

    # ------------------------------------------------------------ session

    @app.get("/v1/health", response_model=m.Health, operation_id="getHealth", tags=["session"])
    def health(request: Request) -> m.Health:
        return m.Health(version=__version__, device=host_device(), auth_required=not is_trusted(request))

    @app.post("/v1/pair", response_model=m.PairResponse, operation_id="pairDevice", tags=["session"],
              responses={403: {"description": "wrong pairing code"}})
    def pair(body: m.PairRequest) -> m.PairResponse:
        token = app.state.pairing.pair(body.code)
        if not token:
            raise HTTPException(403, "wrong pairing code")
        return m.PairResponse(token=token)

    @app.get("/v1/profiles", response_model=list[m.ProfileInfo], operation_id="listProfiles", tags=["session"],
             dependencies=[Depends(auth)])
    def list_profiles() -> list[m.ProfileInfo]:
        out = []
        for p in profiles.PROFILES.values():
            pipe = p.build("-", {})
            out.append(m.ProfileInfo(name=p.name, pipeline=p.pipeline, description=p.description, validated=p.validated,
                                     stages=[s.name for s in pipe.stages]))
        return out

    # ------------------------------------------------------------ audio + jobs

    @app.post("/v1/audio", response_model=m.AudioRef, status_code=201, operation_id="uploadAudio", tags=["jobs"],
              dependencies=[Depends(auth)])
    def upload_audio(file: UploadFile = File(...)) -> m.AudioRef:
        return store_upload(file)

    def store_upload(file: UploadFile) -> m.AudioRef:
        up = settings.uploads_dir
        tmp = up / f".upload-{secrets.token_hex(8)}"
        h, size = hashlib.sha256(), 0
        with tmp.open("wb") as f:
            while chunk := file.file.read(1 << 20):
                h.update(chunk)
                size += len(chunk)
                f.write(chunk)
        digest = h.hexdigest()
        name = Path(file.filename or "audio.wav").name
        suffix = Path(name).suffix.lower() or ".wav"
        audio_id = digest[:16]
        dst = up / f"{audio_id}{suffix}"
        if dst.exists():
            tmp.unlink()
        else:
            shutil.move(tmp, dst)
        (up / f"{audio_id}.json").write_text(json.dumps({"audio_id": audio_id, "sha256": digest, "filename": name,
                                                         "bytes": size, "path": dst.name}))
        return m.AudioRef(audio_id=audio_id, sha256=digest, filename=name, bytes=size)

    def audio_path(audio_id: str) -> tuple[Path, dict]:
        meta = settings.uploads_dir / f"{audio_id}.json"
        if "/" in audio_id or ".." in audio_id or not meta.exists():
            raise HTTPException(404, f"no audio {audio_id}")
        d = json.loads(meta.read_text())
        return settings.uploads_dir / d["path"], d

    def job_input(body: m.JobCreate) -> tuple[Path, str]:
        given = [x for x in (body.audio_id, body.source_id, body.path) if x]
        if len(given) != 1:
            raise HTTPException(422, "give exactly one of audio_id, source_id, path")
        if body.audio_id:
            path, meta = audio_path(body.audio_id)
            return path, meta["filename"]
        if body.source_id:
            p = inspection.resolve_source(settings, body.source_id)
            if not p:
                raise HTTPException(404, f"no source {body.source_id}")
            return p, p.parent.name + ".wav" if p.name == "mix.wav" else p.name
        p = Path(body.path)
        p = p if p.is_absolute() else settings.data_dir / p
        if not inspection.inside(settings.data_dir, p) or not p.is_file():
            raise HTTPException(404, "path must be an existing file inside the data directory")
        return p, p.name

    @app.post("/v1/jobs", response_model=m.Job, status_code=202, operation_id="createJob", tags=["jobs"],
              dependencies=[Depends(auth)])
    def create_job(body: m.JobCreate) -> m.Job:
        if body.profile not in profiles.PROFILES:
            raise HTTPException(422, f"unknown profile {body.profile}; choose from {', '.join(profiles.PROFILES)}")
        path, filename = job_input(body)
        title = body.title or profiles.default_title(body.profile, Path(filename))
        job = jobs.submit(path, body.profile, audio_id=body.audio_id, title=title,
                          params={"audio": body.render_audio}, allow_heavy=body.allow_heavy)
        return job_model(job)

    @app.post("/v1/jobs/{job_id}/rerun", response_model=m.Job, status_code=202, operation_id="rerunJob", tags=["jobs"],
              dependencies=[Depends(auth)])
    def rerun_job(job_id: str, body: m.RerunRequest | None = None) -> m.Job:
        """Run a job again from its manifest (same input, profile, title and parameters)."""
        old = job_or_404(job_id)
        body = body or m.RerunRequest()
        if not old.audio_path.exists():
            raise HTTPException(409, f"input {old.audio_path} no longer exists")
        job = jobs.submit(old.audio_path, old.profile, audio_id=old.audio_id, title=old.title, params=old.params,
                          allow_heavy=body.allow_heavy, cold=set(body.cold), previous_run_id=old.id)
        return job_model(job)

    @app.post("/v1/jobs/upload", response_model=m.Job, status_code=202, operation_id="createJobFromUpload",
              tags=["jobs"], dependencies=[Depends(auth)])
    def create_job_from_upload(file: UploadFile = File(...), profile: str = Form("orchestra-with-soloist"),
                               title: str | None = Form(None), render_audio: bool = Form(True)) -> m.Job:
        """Upload audio and start a job in one request (same as uploadAudio followed by createJob)."""
        ref = store_upload(file)
        return create_job(m.JobCreate(audio_id=ref.audio_id, profile=profile, title=title, render_audio=render_audio))

    @app.get("/v1/jobs", response_model=list[m.Job], operation_id="listJobs", tags=["jobs"], dependencies=[Depends(auth)])
    def list_jobs() -> list[m.Job]:
        return [job_model(j) for j in jobs.list()]

    @app.get("/v1/jobs/{job_id}", response_model=m.Job, operation_id="getJob", tags=["jobs"], dependencies=[Depends(auth)])
    def get_job(job_id: str) -> m.Job:
        return job_model(job_or_404(job_id))

    @app.delete("/v1/jobs/{job_id}", response_model=m.Job, operation_id="cancelJob", tags=["jobs"],
                dependencies=[Depends(auth)])
    def cancel_job(job_id: str) -> m.Job:
        job_or_404(job_id)
        return job_model(jobs.cancel(job_id))

    @app.delete("/v1/runs/{job_id}", status_code=204, operation_id="deleteRun", tags=["jobs"],
                dependencies=[Depends(auth)], response_class=Response,
                responses={404: {"description": "unknown run"}, 409: {"description": "run is queued or running"}})
    def delete_run(job_id: str) -> Response:
        """Delete a finished run (its directory under data/runs); cached artifacts stay. Use cancelJob to stop one."""
        result = jobs.delete(job_id)
        if result == "unknown":
            raise HTTPException(404, f"no run {job_id}")
        if result == "active":
            raise HTTPException(409, f"run {job_id} is still queued or running; cancel it first")
        return Response(status_code=204)

    @app.get("/v1/jobs/{job_id}/events", operation_id="streamJobEvents", tags=["jobs"], dependencies=[Depends(auth)],
             response_class=StreamingResponse,
             responses={200: {"description": "Server-Sent Events; each `data:` line is a JobEvent",
                              "content": {"text/event-stream": {"schema": m.JobEvent.model_json_schema(
                                  ref_template="#/components/schemas/{model}")}}}})
    def stream_events(job_id: str, after: int = Query(-1, description="resume after this event id"),
                      last_event_id: str | None = Header(None)) -> StreamingResponse:
        job = job_or_404(job_id)
        start = int(last_event_id) if last_event_id and last_event_id.lstrip("-").isdigit() else after

        def gen():
            last = start
            while True:
                batch = job.events_after(last, HEARTBEAT_S)
                for e in batch:
                    last = e["id"]
                    yield f"id: {e['id']}\nevent: {e.get('type', 'message')}\ndata: {json.dumps(e)}\n\n"
                if not batch:
                    if job.status in TERMINAL:
                        return
                    yield ": keepalive\n\n"
                elif job.status in TERMINAL and not job.events_after(last, 0):
                    return

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/jobs/{job_id}/manifest", response_model=m.Manifest, operation_id="getJobManifest", tags=["jobs"],
             dependencies=[Depends(auth)])
    def get_manifest(job_id: str):
        p = jobs.run_dir(job_or_404(job_id).id) / "manifest.json"
        if not p.exists():
            raise HTTPException(404, "manifest not written yet")
        return JSONResponse(json.loads(p.read_text()))

    @app.get("/v1/jobs/{job_id}/artifacts", response_model=list[m.Artifact], operation_id="listJobArtifacts",
             tags=["results"], dependencies=[Depends(auth)])
    def list_artifacts(job_id: str) -> list[m.Artifact]:
        job = job_or_404(job_id)
        d = jobs.run_dir(job.id) / "outputs"
        return [m.Artifact(name=n, bytes=(d / n).stat().st_size, media_type=MEDIA.get(n, "application/octet-stream"),
                           url=f"/v1/jobs/{job.id}/artifacts/{n}") for n in outputs_of(job)]

    @app.get("/v1/jobs/{job_id}/artifacts/{name:path}", operation_id="getJobArtifact", tags=["results"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_artifact(job_id: str, name: str):
        return output_file(job_id, name)

    @app.get("/v1/jobs/{job_id}/composition", operation_id="getComposition", tags=["results"],
             dependencies=[Depends(auth)], response_model=m.Composition,
             responses={200: {"description": "Composition JSON, byte for byte as written by the pipeline"}})
    def get_composition(job_id: str):
        return output_file(job_id, "composition.json")

    @app.get("/v1/jobs/{job_id}/musicxml", operation_id="getMusicXml", tags=["results"], dependencies=[Depends(auth)],
             response_class=FileResponse,
             responses={200: {"content": {"application/vnd.recordare.musicxml+xml": {"schema": {"type": "string"}}}}})
    def get_musicxml(job_id: str):
        return output_file(job_id, "brass-band.musicxml")

    @app.get("/v1/jobs/{job_id}/pdf", operation_id="getPdf", tags=["results"], dependencies=[Depends(auth)],
             response_class=FileResponse,
             responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}})
    def get_pdf(job_id: str):
        return output_file(job_id, "brass-band.pdf")

    @app.get("/v1/jobs/{job_id}/midi", operation_id="getMidi", tags=["results"], dependencies=[Depends(auth)],
             response_class=FileResponse,
             responses={200: {"content": {"audio/midi": {"schema": {"type": "string", "format": "binary"}}}}})
    def get_midi(job_id: str):
        return output_file(job_id, "brass-band.mid")

    @app.get("/v1/jobs/{job_id}/audio", operation_id="getRenderedAudio", tags=["results"], dependencies=[Depends(auth)],
             response_class=FileResponse,
             responses={200: {"content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}}})
    def get_audio(job_id: str):
        return output_file(job_id, "brass-band.mp3")

    # ------------------------------------------------------------ benchmarks

    @app.get("/v1/suites", response_model=list[m.SuiteInfo], operation_id="listSuites", tags=["benchmarks"],
             dependencies=[Depends(auth)])
    def list_suites() -> list[m.SuiteInfo]:
        from brasscribe_eval import suites

        return [m.SuiteInfo(name=s.name, description=s.description, cpu=s.cpu, requires=list(s.requires))
                for s in suites.SUITES.values()]

    @app.post("/v1/suites/{name}/run", response_model=m.BenchRun, operation_id="runSuite", tags=["benchmarks"],
              dependencies=[Depends(auth)])
    def run_suite(name: str, mode: str = Query("cached", pattern="^(cached|live)$")) -> m.BenchRun:
        """Run a suite or group (cpu, all) against eval/baselines.json; the result is stored in the history."""
        from brasscribe_eval import suites

        if name not in suites.SUITES and name not in suites.GROUPS:
            raise HTTPException(404, f"no suite {name}")
        report = suites.gate(suites.run_many(name, mode=mode, data=settings.data_dir))
        return m.BenchRun(**history.save(settings, report, name, mode))

    @app.get("/v1/suites/history", response_model=list[m.SuiteHistoryEntry], operation_id="listSuiteHistory",
             tags=["benchmarks"], dependencies=[Depends(auth)])
    def suite_history(suite: str | None = Query(None, description="only results of this suite"),
                      limit: int = Query(1000, ge=1, le=10000)) -> list[m.SuiteHistoryEntry]:
        """Every stored suite result, newest first (from `brasscribe bench` and runSuite)."""
        return [m.SuiteHistoryEntry(**r) for r in history.entries(settings, suite, limit)]

    # ------------------------------------------------------------ inspection

    def file_ref(path: Path, name: str, url: str, sha256: str | None = None) -> m.FileRef:
        return m.FileRef(name=name, bytes=path.stat().st_size if path.exists() else 0, media_type=media_type(name),
                         url=url, sha256=sha256)

    def safe_file(root: Path, rel: str) -> Path:
        p = (root / rel).resolve()
        if not inspection.inside(root, p) or p == root.resolve() or not p.is_file():
            raise HTTPException(404, f"{rel} not found")
        return p

    @app.get("/v1/jobs/{job_id}/input", operation_id="getJobInput", tags=["inspection"], dependencies=[Depends(auth)],
             response_class=FileResponse, responses={200: {"content": {"audio/wav": {}}}})
    def get_input(job_id: str):
        """The job's original input audio (for A/B listening)."""
        job = job_or_404(job_id)
        if not job.audio_path.is_file():
            raise HTTPException(404, "input audio no longer exists")
        return FileResponse(job.audio_path, media_type=media_type(job.audio_path.name), filename=job.audio_path.name)

    @app.get("/v1/jobs/{job_id}/stages", response_model=list[m.StageArtifacts], operation_id="listJobStages",
             tags=["inspection"], dependencies=[Depends(auth)])
    def list_stages(job_id: str) -> list[m.StageArtifacts]:
        """Every stage of a run with its output files (stems, layers, MIDI, beats, Composition, MusicXML ...)."""
        job = job_or_404(job_id)
        run_dir = jobs.run_dir(job.id)
        mpath = run_dir / "manifest.json"
        recorded = {s["stage"]: s for s in json.loads(mpath.read_text()).get("stages", [])} if mpath.exists() else {}
        out = []
        for name, st in job.stages.items():
            rec = recorded.get(name, {})
            d = run_dir / "stages" / name
            files = rec.get("outputs")
            if files is None:
                files = {p.relative_to(d).as_posix(): None for p in sorted(d.rglob("*")) if p.is_file()} if d.is_dir() else {}
            out.append(m.StageArtifacts(
                stage=name, kind=st.get("kind"), status=st["status"], key=rec.get("key"), seconds=st.get("seconds"),
                device=st.get("device"),
                files=[file_ref(d / f, f, f"/v1/jobs/{job.id}/stages/{name}/files/{f}", h) for f, h in files.items()]))
        return out

    @app.get("/v1/jobs/{job_id}/stages/{stage}/files/{name:path}", operation_id="getStageFile", tags=["inspection"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_stage_file(job_id: str, stage: str, name: str):
        job = job_or_404(job_id)
        if stage not in job.stages:
            raise HTTPException(404, f"no stage {stage} in job {job_id}")
        p = safe_file(jobs.run_dir(job.id) / "stages" / stage, name)
        return FileResponse(p, media_type=media_type(name), filename=p.name)

    @app.get("/v1/references", response_model=list[m.Reference], operation_id="listReferences", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_references() -> list[m.Reference]:
        """Reference outputs under <data>/golden (read only)."""
        root = settings.golden_dir
        out = []
        for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
            out.append(m.Reference(name=d.name, files=[
                file_ref(f, f.name, f"/v1/references/{d.name}/files/{f.name}") for f in sorted(d.iterdir()) if f.is_file()]))
        return out

    @app.get("/v1/references/{name}/files/{file}", operation_id="getReferenceFile", tags=["inspection"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_reference_file(name: str, file: str):
        if "/" in name or name in ("", ".", "..") or not (settings.golden_dir / name).is_dir():
            raise HTTPException(404, f"no reference {name}")
        p = safe_file(settings.golden_dir / name, file)
        return FileResponse(p, media_type=media_type(file), filename=p.name)

    @app.get("/v1/jobs/{job_id}/compare", response_model=m.Comparison, operation_id="compareJob", tags=["inspection"],
             dependencies=[Depends(auth)])
    def compare_job(job_id: str, reference: str | None = Query(None, description="name from listReferences"),
                    job: str | None = Query(None, description="another job id")) -> m.Comparison:
        """composition.json byte equality and per-part MusicXML note content against a reference or another job."""
        from .compare import compare

        this = jobs.run_dir(job_or_404(job_id).id) / "outputs"
        if bool(reference) == bool(job):
            raise HTTPException(422, "give exactly one of reference, job")
        other = settings.golden_dir / reference if reference else jobs.run_dir(job_or_404(job).id) / "outputs"
        if reference and ("/" in reference or reference in (".", "..") or not other.is_dir()):
            raise HTTPException(404, f"no reference {reference}")
        for d in (this, other):
            if not (d / "composition.json").exists() or not (d / "brass-band.musicxml").exists():
                raise HTTPException(404, f"no score output in {d.name}")
        return m.Comparison(**compare(this, other).to_dict())

    def roundtrip_file(job_id: str) -> Path:
        return jobs.run_dir(job_or_404(job_id).id) / "roundtrip.json"

    @app.get("/v1/jobs/{job_id}/roundtrip", response_model=m.Roundtrip, operation_id="getRoundtrip",
             tags=["inspection"], dependencies=[Depends(auth)])
    def get_roundtrip(job_id: str) -> m.Roundtrip:
        """Stored MuseScore round-trip result, or status not_run (start it with runRoundtrip)."""
        p = roundtrip_file(job_id)
        return m.Roundtrip(**json.loads(p.read_text())) if p.exists() else m.Roundtrip(status="not_run")

    @app.post("/v1/jobs/{job_id}/roundtrip", response_model=m.Roundtrip, operation_id="runRoundtrip",
              tags=["inspection"], dependencies=[Depends(auth)])
    def run_roundtrip(job_id: str) -> m.Roundtrip:
        """Re-export the job's MusicXML through MuseScore and compare every part's sounding pitches (takes seconds)."""
        outputs = jobs.run_dir(job_or_404(job_id).id) / "outputs"
        if not (outputs / "brass-band.musicxml").exists():
            raise HTTPException(404, "job has no MusicXML output")
        r = inspection.roundtrip(outputs)
        if r["status"] != "not_run":
            roundtrip_file(job_id).write_text(json.dumps(r, indent=1))
        return m.Roundtrip(**r)

    @app.get("/v1/jobs/{job_id}/validation", response_model=list[m.ValidationIssue], operation_id="getValidation",
             tags=["inspection"], dependencies=[Depends(auth)])
    def get_validation(job_id: str) -> list[m.ValidationIssue]:
        """Arranger warnings (range problems) for the job's Composition, by part, bar and beat."""
        run_dir = jobs.run_dir(job_or_404(job_id).id)
        comp = run_dir / "outputs" / "composition.json"
        if not comp.exists():
            raise HTTPException(404, "job has no Composition output")
        cached = run_dir / "validation.json"
        if cached.exists() and cached.stat().st_mtime >= comp.stat().st_mtime:
            issues = json.loads(cached.read_text())
        else:
            issues = inspection.validation(comp)
            cached.write_text(json.dumps(issues, indent=1))
        return [m.ValidationIssue(**i) for i in issues]

    @app.get("/v1/sources", response_model=list[m.Source], operation_id="listSources", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_sources() -> list[m.Source]:
        """Recordings that can start a job without an upload: captures and eval-set items (createJob source_id)."""
        return [m.Source(**x) for x in inspection.sources(settings)]

    @app.get("/v1/registry/adapters", response_model=list[m.AdapterInfo], operation_id="listAdapters",
             tags=["inspection"], dependencies=[Depends(auth)])
    def list_adapters() -> list[m.AdapterInfo]:
        """Adapters with version, environment fingerprint, device, licence and model weights."""
        from .adapters import ADAPTERS, AdapterRegistry
        from .hashing import HashIndex

        hashes = HashIndex(settings.cache_dir / "file-hashes.json")
        reg = AdapterRegistry(settings.adapters_dir, settings.models_dir, hashes, settings.gpu_lock)
        out = [m.AdapterInfo(**reg.describe(n)) for n in ADAPTERS]
        hashes.save()
        return out

    @app.get("/v1/registry/datasets", response_model=list[m.Dataset], operation_id="listDatasets", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_datasets() -> list[m.Dataset]:
        """Eval sets under <data>/eval: size, items, licence, cached model outputs and how to build a missing set."""
        return [m.Dataset(**d) for d in inspection.datasets(settings)]

    @app.get("/v1/parity", response_model=list[m.Manifest], operation_id="listParityReports", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_parity() -> list[dict]:
        """Model-conversion parity reports as written (every *.json in BRASSCRIBE_PARITY_REPORTS), plus `_file`."""
        return history.reports(settings.parity_reports_dir)

    @app.get("/v1/conformance", response_model=list[m.Manifest], operation_id="listConformanceReports",
             tags=["inspection"], dependencies=[Depends(auth)])
    def list_conformance() -> list[dict]:
        """Rust-core conformance results as written (every *.json in BRASSCRIBE_CONFORMANCE_REPORTS), plus `_file`."""
        return history.reports(settings.conformance_reports_dir)

    if STATIC.is_dir():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="studio")
    return app
