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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, profiles
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
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def job_model(job: Job) -> m.Job:
        stages = list(job.stages.values())
        done = sum(s["status"] in ("cached", "imported", "ran", "skipped") for s in stages)
        return m.Job(id=job.id, profile=job.profile, title=job.title, audio_id=job.audio_id, status=job.status,
                     created=job.created, started=job.started, finished=job.finished, error=job.error,
                     progress=round(done / len(stages), 4) if stages else 0.0,
                     stages=[m.StageState(**s) for s in stages], outputs=outputs_of(job))

    def output_file(job_id: str, name: str) -> FileResponse:
        job = job_or_404(job_id)
        if name == "manifest.json":
            p = jobs.run_dir(job.id) / "manifest.json"
        else:
            p = jobs.run_dir(job.id) / "outputs" / name
        if "/" in name or ".." in name or not p.is_file():
            raise HTTPException(404, f"{name} not available for job {job_id} (status {job.status})")
        return FileResponse(p, media_type=MEDIA.get(name, "application/octet-stream"), filename=name)

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

    @app.post("/v1/jobs", response_model=m.Job, status_code=202, operation_id="createJob", tags=["jobs"],
              dependencies=[Depends(auth)])
    def create_job(body: m.JobCreate) -> m.Job:
        if body.profile not in profiles.PROFILES:
            raise HTTPException(422, f"unknown profile {body.profile}; choose from {', '.join(profiles.PROFILES)}")
        path, meta = audio_path(body.audio_id)
        title = body.title or profiles.default_title(body.profile, Path(meta["filename"]))
        job = jobs.submit(path, body.profile, audio_id=body.audio_id, title=title,
                          params={"audio": body.render_audio}, allow_heavy=body.allow_heavy)
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

    @app.get("/v1/jobs/{job_id}/artifacts/{name}", operation_id="getJobArtifact", tags=["results"],
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

    @app.post("/v1/suites/{name}/run", response_model=list[m.SuiteResult], operation_id="runSuite", tags=["benchmarks"],
              dependencies=[Depends(auth)])
    def run_suite(name: str, mode: str = Query("cached", pattern="^(cached|live)$")) -> list[m.SuiteResult]:
        from brasscribe_eval import suites

        if name not in suites.SUITES and name not in suites.GROUPS:
            raise HTTPException(404, f"no suite {name}")
        report = suites.gate(suites.run_many(name, mode=mode, data=settings.data_dir))
        return [m.SuiteResult(**r) for r in report["suites"]]

    if STATIC.is_dir():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="studio")
    return app
