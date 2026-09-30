"""HTTP service: Studio (browser, same machine) and companion mode for the native Play apps.

Clients on the loopback interface are trusted (BRASSCRIBE_TRUST_LOCAL, on by
default). Any other client pairs once: `POST /v1/pair` with the code the engine
shows returns that device's own bearer token, and every other request carries
`Authorization: Bearer <token>`. The token survives engine restarts and address
changes; every authenticated request marks the device as seen, which is what
`online` in `/v1/devices` reports.

The owner manages devices on the computer (`/v1/status`, `/v1/devices`,
`/v1/pairing*`). Those endpoints trust loopback only while no admin token is
configured; with BRASSCRIBE_ADMIN_TOKEN (or _FILE) set they require
`Authorization: Bearer <admin token>`, because a proxy on the same machine makes
remote traffic look local. See companion.py, config.py and
docs/plan/pairing-and-remote-access.md.

Progress is streamed as Server-Sent Events with monotonic ids; reconnect with
`Last-Event-ID` (or `?after=`) to resume. A comment line is sent every 15 s
while nothing happens.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal

import anyio

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, build_info, history, inspection, profiles
from .companion import DeviceRegistry, PairingWindow, PairRequests, ServerIdentity, iso, pairing_uri
from . import schemas as m
from .adapters import host_device
from .config import Settings
from .guard import BodyLimit, RequestGuard
from .jobs import TERMINAL, Job, JobManager
from .names import is_audio, valid_id, valid_relpath
from .uploads import UploadRoute, UploadSink

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
# Studio's own files keep their names across releases, so the browser revalidates them on every load
# (a 304 via the ETag) instead of guessing a freshness lifetime and running an old studio.js after an
# update. The band SoundFont is large and changes only with a new sound build: a day before revalidating.
STUDIO_CACHE = "no-cache"
BAND_SOUNDS_CACHE = "public, max-age=86400"
STATIC = Path(__file__).resolve().parent / "static"
BAND_SOUND_FILES = ("brasscribe-band.sf2", "mapping.json")  # what Studio needs from BRASSCRIBE_BAND_SOUNDS_DIR
HEARTBEAT_S = 15.0
# Event streams wait on their job in threads of their own: in the shared pool (40 threads) forty open
# streams would leave no thread for any other request.
STREAM_WAITERS = 256
ROTATE_AFTER_S = 30 * 86400.0  # clients are asked to rotate their token monthly

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
                ".beats": "text/plain", ".brf": "text/plain; charset=us-ascii", ".html": "text/html; charset=utf-8",
                ".txt": "text/plain; charset=utf-8"}


def media_type(name: str) -> str:
    return MEDIA.get(name) or SUFFIX_MEDIA.get(Path(name).suffix, "application/octet-stream")


class CachedStaticFiles(StaticFiles):
    """StaticFiles with a Cache-Control header on every file, 200 and 304 alike."""

    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = self.cache_control
        return response


def create_app(settings: Settings | None = None, *, trust_loopback: bool | None = None, workers: int = 1) -> FastAPI:
    """`trust_loopback` overrides settings.trust_local (BRASSCRIBE_TRUST_LOCAL)."""
    settings = (settings or Settings()).ensure()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.devices.flush()  # presence kept in memory reaches devices.json
        # A job still running would otherwise keep the engine alive, and its model running, until it finished.
        await anyio.to_thread.run_sync(app.state.jobs.shutdown)

    app = FastAPI(
        lifespan=lifespan,
        title="brasscribe engine",
        version=__version__,
        description="Recording in, brass-band score out. Jobs run a profile's stage DAG with a content-addressed "
                    "cache; progress streams as Server-Sent Events. Loopback clients are trusted; LAN clients pair "
                    "once with the code the engine shows and then send their own long-lived bearer token.",
    )
    app.router.route_class = UploadRoute  # uploads go straight into the uploads folder (uploads.py)
    app.state.settings = settings
    app.state.jobs = JobManager(settings, workers=workers)
    stream_waiters = anyio.CapacityLimiter(STREAM_WAITERS)
    app.state.trust_loopback = settings.trust_local if trust_loopback is None else trust_loopback
    app.state.admin_token = settings.admin_credential()
    from .discovery import service_name

    app.state.identity = ServerIdentity.load(settings.state_dir)
    app.state.server_name = service_name()
    app.state.devices = DeviceRegistry(settings.state_dir / "devices.json", idle_days=settings.device_idle_days)
    # The code printed at start stays valid until pairing is closed, as before; a window opened on the
    # computer (POST /v1/pairing) is single-use and expires.
    app.state.pairing = PairingWindow()
    app.state.pair_requests = PairRequests()
    app.state.hosts = []  # ip:port the engine is reachable on; set by `brasscribe serve`

    def trusted_address(host: str) -> bool:
        return app.state.trust_loopback and host in LOOPBACK | {"testclient"}

    def is_trusted(request: Request) -> bool:
        return trusted_address(request.client.host if request.client else "")

    app.add_middleware(BodyLimit, max_bytes=settings.max_upload_bytes)
    app.add_middleware(RequestGuard, trusted=trusted_address, allowed_hosts=settings.allowed_hosts)

    def bearer(authorization: str | None) -> str | None:
        return authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None

    def is_admin(request: Request) -> bool:
        admin, token = app.state.admin_token, bearer(request.headers.get("authorization"))
        return bool(admin and token and hmac.compare_digest(token.encode(), admin.encode()))

    def auth(request: Request, authorization: str | None = Header(None)) -> None:
        request.state.device = None
        if is_trusted(request) or is_admin(request):
            return
        token = bearer(authorization)
        if token and settings.token and hmac.compare_digest(token.encode(), settings.token.encode()):
            return
        device = app.state.devices.authenticate(token) if token else None
        if device is None:
            raise HTTPException(401, "pair first: POST /v1/pair with the engine's pairing code", {"WWW-Authenticate": "Bearer"})
        request.state.device = device

    def owner(request: Request) -> None:
        """Device management happens on the computer running the engine: the admin token when one is
        configured, else a loopback client while local trust is on. Device tokens never qualify."""
        if is_admin(request):
            return
        if app.state.admin_token:
            raise HTTPException(403, "needs the engine's admin token")
        if not is_trusted(request):
            raise HTTPException(403, "only on the computer running the engine")

    def this_device(request: Request, _: None = Depends(auth)):
        if request.state.device is None:
            raise HTTPException(404, "this client is not a paired device (loopback or static token)")
        return request.state.device

    def pair_response(device, token: str) -> m.PairResponse:
        return m.PairResponse(token=token, device_id=device.device_id, server_id=app.state.identity.server_id,
                              server_name=app.state.server_name)

    def pairing_state() -> m.PairingState:
        w: PairingWindow = app.state.pairing
        is_open = w.is_open
        code = w.code if is_open else None
        return m.PairingState(open=is_open, code=code, expires_at=iso(w.expires_at) if is_open and w.expires_at else None,
                              single_use=w.single_use, server_id=app.state.identity.server_id,
                              server_name=app.state.server_name, hosts=list(app.state.hosts), fingerprint=None,
                              uri=pairing_uri(app.state.identity.server_id, app.state.server_name,
                                              list(app.state.hosts), code),
                              locked_until=iso(w.locked_until) if w.retry_after() > 0 else None)

    def request_info(r) -> m.PairRequestInfo:
        """A pairing request as both sides see it; `name_in_use` when another paired device has the same name."""
        taken = {d.name.casefold() for d in app.state.devices.list() if d.device_id != r.device_id}
        return m.PairRequestInfo(**r.public(), name_in_use=r.name.casefold() in taken)

    jobs: JobManager = app.state.jobs
    from .conformance import ConformanceRunner

    conformance_runner = app.state.conformance = ConformanceRunner(settings.conformance_reports_dir)

    def job_or_404(job_id: str) -> Job:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"no job {job_id}")
        return job

    def outputs_of(job: Job) -> list[str]:
        return jobs.outputs(job)

    def job_model(job: Job) -> m.Job:
        stages = list(job.stages.values())
        done = sum(s["status"] in ("cached", "imported", "ran", "skipped") for s in stages)
        return m.Job(id=job.id, profile=job.profile, title=job.title, audio_id=job.audio_id, status=job.status,
                     created=job.created, started=job.started, finished=job.finished, error=job.error,
                     progress=round(done / len(stages), 4) if stages else 0.0, previous_run_id=job.previous_run_id,
                     device_name=job.device_name,
                     stages=[m.StageState(**s) for s in stages], outputs=outputs_of(job))

    def output_file(job_id: str, name: str) -> FileResponse:
        job = job_or_404(job_id)
        if not valid_relpath(name):
            raise HTTPException(404, f"{name} not available for job {job_id}")
        root = jobs.run_dir(job.id) if name == "manifest.json" else jobs.run_dir(job.id) / "outputs"
        p = (root / name).resolve()
        if not inspection.inside(root, p) or not p.is_file():
            raise HTTPException(404, f"{name} not available for job {job_id} (status {job.status})")
        return FileResponse(p, media_type=media_type(name), filename=p.name)

    # ------------------------------------------------------------ session

    @app.get("/v1/health", response_model=m.Health, operation_id="getHealth", tags=["session"])
    def health(request: Request) -> m.Health:
        return m.Health(version=__version__, build=build_info.build(), device=host_device(),
                        auth_required=not is_trusted(request), server_id=app.state.identity.server_id,
                        server_name=app.state.server_name)

    @app.post("/v1/pair", response_model=m.PairResponse, operation_id="pairDevice", tags=["session"],
              responses={403: {"description": "wrong pairing code, or pairing is closed"},
                         429: {"description": "too many wrong codes; retry after Retry-After seconds"}})
    def pair(body: m.PairRequest, request: Request, authorization: str | None = Header(None)) -> m.PairResponse:
        client = request.client.host if request.client else ""
        result = app.state.pairing.check(body.code, client)
        if result == "locked":
            raise HTTPException(429, "too many wrong codes; wait and try again",
                                {"Retry-After": str(int(app.state.pairing.retry_after(client)) + 1)})
        if result == "closed":
            raise HTTPException(403, "pairing is closed: open it on the computer")
        if result != "ok":
            raise HTTPException(403, "wrong pairing code")
        # A device that pairs again while holding a valid token keeps its entry instead of adding a duplicate.
        token = bearer(authorization)
        known = app.state.devices.authenticate(token) if token else None
        device, new_token = app.state.devices.pair(body.device_name, body.platform,
                                                   replace=known.device_id if known else None)
        return pair_response(device, new_token)

    @app.post("/v1/pair/requests", response_model=m.PairRequestInfo, status_code=202, operation_id="requestPairing",
              tags=["session"], responses={429: {"description": "too many requests are waiting"}})
    def request_pairing(body: m.PairRequestCreate, request: Request) -> m.PairRequestInfo:
        """Ask to pair without a code. The computer shows 'Allow <device>?' with the same four-digit match code;
        poll GET /v1/pair/requests/{request_id} until it is approved or denied (requests expire after 2 minutes).
        A new request from the same address replaces the one it has waiting."""
        r = app.state.pair_requests.create(body.device_name, body.platform,
                                           request.client.host if request.client else "")
        if r is None:
            raise HTTPException(429, "too many pairing requests are waiting", {"Retry-After": "30"})
        return request_info(r)

    @app.get("/v1/pair/requests/{request_id}", response_model=m.PairRequestResult, operation_id="pollPairingRequest",
             tags=["session"], responses={404: {"description": "unknown or expired request"}})
    def poll_pairing_request(request_id: str) -> m.PairRequestResult:
        r = app.state.pair_requests.poll(request_id)
        if r is None:
            raise HTTPException(404, "unknown or expired pairing request")
        if r.status != "approved":
            return m.PairRequestResult(status=r.status)
        return m.PairRequestResult(status="approved", token=r.token, device_id=r.device_id,
                                   server_id=app.state.identity.server_id, server_name=app.state.server_name)

    # ------------------------------------------------------------ this device

    @app.get("/v1/devices/me", response_model=m.DeviceSelf, operation_id="getThisDevice", tags=["devices"],
             responses={401: {"description": "the credential is unknown or revoked: pair again"},
                        404: {"description": "connected, but not as a paired device (a trusted client on the "
                                           "engine's own computer, or the static token); not a revocation"}})
    def get_this_device(device=Depends(this_device)) -> m.DeviceSelf:
        """Check the stored credential, and the paired device's heartbeat (every 20 s while the app is open;
        it keeps the device `online`). 401 means pair again; anything else means the credential is still good.

        A client on the engine's own computer is trusted without pairing (GET /v1/health says
        `auth_required: false`) and gets 404 here; it uses GET /v1/health as its heartbeat instead and is
        not counted as an online device."""
        rotate_from = device.rotated_at or device.paired_at
        return m.DeviceSelf(**app.state.devices.public(device), server_id=app.state.identity.server_id,
                            rotate_after=iso(rotate_from + ROTATE_AFTER_S),
                            expires_if_idle_after=iso(device.last_seen + app.state.devices.idle_s))

    @app.post("/v1/devices/me/rotate", response_model=m.RotateResponse, operation_id="rotateDeviceToken",
              tags=["devices"])
    def rotate_device_token(device=Depends(this_device), authorization: str | None = Header(None)) -> m.RotateResponse:
        token = app.state.devices.rotate(device.device_id, bearer(authorization))
        if token is None:
            raise HTTPException(401, "this device was revoked")
        return m.RotateResponse(token=token, device_id=device.device_id)

    @app.delete("/v1/devices/me", status_code=204, operation_id="unpairThisDevice", tags=["devices"],
                response_class=Response)
    def unpair_this_device(device=Depends(this_device)) -> Response:
        app.state.devices.revoke(device.device_id)
        return Response(status_code=204)

    # ------------------------------------------------------------ owner, on the computer

    @app.get("/v1/devices", response_model=list[m.DeviceInfo], operation_id="listDevices", tags=["devices"],
             dependencies=[Depends(owner)])
    def list_devices() -> list[m.DeviceInfo]:
        return [m.DeviceInfo(**app.state.devices.public(d)) for d in app.state.devices.list()]

    @app.get("/v1/status", response_model=m.EngineStatus, operation_id="getStatus", tags=["devices"],
             dependencies=[Depends(owner)])
    def get_status() -> m.EngineStatus:
        """For the desktop helper: who is connected, whether pairing is open, what the engine is doing."""
        devices = app.state.devices.list()
        running, queued = jobs.counts()
        return m.EngineStatus(server_id=app.state.identity.server_id, server_name=app.state.server_name,
                              version=__version__, online_devices=sum(map(app.state.devices.is_online, devices)),
                              paired_devices=len(devices), pairing_open=app.state.pairing.is_open,
                              jobs_running=running, jobs_queued=queued)

    @app.delete("/v1/devices/{device_id}", status_code=204, operation_id="revokeDevice", tags=["devices"],
                dependencies=[Depends(owner)], response_class=Response,
                responses={404: {"description": "no such device"}})
    def revoke_device(device_id: str) -> Response:
        if not app.state.devices.revoke(device_id):
            raise HTTPException(404, "no such device")
        return Response(status_code=204)

    @app.get("/v1/pairing", response_model=m.PairingState, operation_id="getPairing", tags=["devices"],
             dependencies=[Depends(owner)])
    def get_pairing() -> m.PairingState:
        return pairing_state()

    @app.post("/v1/pairing", response_model=m.PairingState, operation_id="openPairing", tags=["devices"],
              dependencies=[Depends(owner)])
    def open_pairing(body: m.PairingOpen | None = None) -> m.PairingState:
        """Show a new code (default: 10 minutes, single use), or extend the one on screen."""
        body = body or m.PairingOpen()
        if not (body.extend and app.state.pairing.extend(body.ttl_s or 600)):
            app.state.pairing.open(body.ttl_s, body.single_use)
        return pairing_state()

    @app.delete("/v1/pairing", response_model=m.PairingState, operation_id="closePairing", tags=["devices"],
                dependencies=[Depends(owner)])
    def close_pairing() -> m.PairingState:
        app.state.pairing.close()
        return pairing_state()

    @app.get("/v1/pairing/requests", response_model=list[m.PairRequestInfo], operation_id="listPairingRequests",
             tags=["devices"], dependencies=[Depends(owner)])
    def list_pairing_requests() -> list[m.PairRequestInfo]:
        return [request_info(r) for r in app.state.pair_requests.pending()]

    @app.post("/v1/pairing/requests/{request_id}/{decision}", response_model=m.PairRequestInfo,
              operation_id="decidePairingRequest", tags=["devices"], dependencies=[Depends(owner)],
              responses={404: {"description": "unknown, expired or already decided"}})
    def decide_pairing_request(request_id: str, decision: Literal["approve", "deny"]) -> m.PairRequestInfo:
        r = app.state.pair_requests.decide(request_id, decision == "approve", app.state.devices)
        if r is None:
            raise HTTPException(404, "unknown, expired or already decided")
        return request_info(r)

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
        if isinstance(file.file, UploadSink):  # already in the uploads folder, hashed as it arrived
            tmp, digest, size = file.file.keep()
        else:
            tmp = up / f".upload-{secrets.token_hex(8)}"
            h, size = hashlib.sha256(), 0
            with tmp.open("wb") as f:
                while chunk := file.file.read(1 << 20):
                    h.update(chunk)
                    size += len(chunk)
                    f.write(chunk)
            digest = h.hexdigest()
        name = Path(file.filename or "audio.wav").name
        # The client's name is only shown; the stored file keeps an audio suffix, never one like .json.
        suffix = Path(name).suffix.lower() if is_audio(name) else ".wav"
        audio_id = digest[:16]
        dst = up / f"{audio_id}{suffix}"
        if dst.exists():
            tmp.unlink()
        else:
            os.replace(tmp, dst)
        (up / f"{audio_id}.meta.json").write_text(json.dumps({"audio_id": audio_id, "sha256": digest, "filename": name,
                                                         "bytes": size, "path": dst.name}))
        return m.AudioRef(audio_id=audio_id, sha256=digest, filename=name, bytes=size)

    def audio_path(audio_id: str) -> tuple[Path, dict]:
        """An upload and its metadata: <id>.meta.json, or <id>.json as engines before it wrote it."""
        if valid_id(audio_id):
            for meta in (settings.uploads_dir / f"{audio_id}.meta.json", settings.uploads_dir / f"{audio_id}.json"):
                try:
                    d = json.loads(meta.read_text())
                    stored = d["path"]
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if isinstance(stored, str) and valid_id(stored) and is_audio(stored):
                    return settings.uploads_dir / stored, d
        raise HTTPException(404, f"no audio {audio_id}")

    def input_allowed(p: Path, anywhere: bool = False) -> bool:
        """Jobs read audio (or video) from the engine's own audio folders: uploads, captures and eval sets.
        `anywhere`: an existing run's input may lie elsewhere (`brasscribe run <file>`), for the owner."""
        roots = (settings.uploads_dir, settings.data_dir / "captures", settings.datasets_dir)
        return is_audio(p) and (anywhere or any(inspection.inside(r, p) for r in roots)) and p.is_file()

    def is_device(request: Request) -> bool:
        return getattr(request.state, "device", None) is not None

    # Paired devices see no paths or details of the computer; Studio and the owner see them in full.
    def shown_path(p: str | Path | None) -> str | None:
        """A path as a paired device sees it: relative to the data folder, else only the file name."""
        if not p:
            return None
        try:
            return Path(p).resolve().relative_to(settings.data_dir.resolve()).as_posix()
        except (ValueError, OSError):
            return Path(p).name

    def device_manifest(manifest: dict) -> dict:
        """A run's manifest without the computer's paths, git state and host details."""
        m = {k: v for k, v in manifest.items() if k not in ("git", "host", "out")}
        if isinstance(m.get("input"), dict):
            m["input"] = {**m["input"], "path": shown_path(m["input"].get("path"))}
        if isinstance(m.get("options"), dict) and "reuse" in m["options"]:
            m["options"] = {**m["options"], "reuse": shown_path(m["options"]["reuse"])}
        if isinstance(m.get("stages"), list):
            m["stages"] = [{**st, "provenance": {k: v for k, v in st["provenance"].items() if k != "imported_from"}}
                           if isinstance(st, dict) and isinstance(st.get("provenance"), dict) else st
                           for st in m["stages"]]
        return m

    def job_input(body: m.JobCreate, request: Request) -> tuple[Path, str]:
        given = [x for x in (body.audio_id, body.source_id, body.path) if x]
        if len(given) != 1:
            raise HTTPException(422, "give exactly one of audio_id, source_id, path")
        if body.audio_id:
            path, meta = audio_path(body.audio_id)
            if not input_allowed(path):
                raise HTTPException(404, f"no audio {body.audio_id}")
            return path, meta["filename"]
        if body.source_id:
            p = inspection.resolve_source(settings, body.source_id)
            if not p or not input_allowed(p):
                raise HTTPException(404, f"no source {body.source_id}")
            return p, p.parent.name + ".wav" if p.name == "mix.wav" else p.name
        if is_device(request):
            raise HTTPException(403, "paired devices start jobs from an upload (audio_id) or a source (source_id)")
        p = settings.data_dir / body.path if valid_relpath(body.path) else None
        if p is None or not input_allowed(p):
            raise HTTPException(404, "path must be an audio file under uploads/, captures/ or eval/ in the data "
                                     "directory, relative to it")
        return p, p.name

    @app.post("/v1/jobs", response_model=m.Job, status_code=202, operation_id="createJob", tags=["jobs"],
              dependencies=[Depends(auth)])
    def create_job(body: m.JobCreate, request: Request) -> m.Job:
        if body.profile not in profiles.PROFILES:
            raise HTTPException(422, f"unknown profile {body.profile}; choose from {', '.join(profiles.PROFILES)}")
        path, filename = job_input(body, request)
        title = body.title or profiles.default_title(body.profile, Path(filename))
        params = {"audio": body.render_audio, "lineup": body.lineup, "difficulty": body.difficulty,
                  "key": body.key, "transpose": body.transpose, "seat": body.seat, "reads": body.reads, "lead": body.lead}
        if not body.muscriptor:
            params["muscriptor"] = False
        try:
            profiles.job_options(body.profile, params)
        except ValueError as e:
            # The apps show their own words for the code; the message is for logs and Studio.
            return JSONResponse({"code": profiles.option_error_code(e), "detail": str(e)}, status_code=422)
        device = getattr(request.state, "device", None)
        job = jobs.submit(path, body.profile, audio_id=body.audio_id, title=title, params=params,
                          allow_heavy=body.allow_heavy, device_name=device.name if device else None)
        return job_model(job)

    @app.post("/v1/jobs/{job_id}/rerun", response_model=m.Job, status_code=202, operation_id="rerunJob", tags=["jobs"],
              dependencies=[Depends(auth)])
    def rerun_job(job_id: str, request: Request, body: m.RerunRequest | None = None) -> m.Job:
        """Run a job again from its manifest (same input, profile, title and parameters)."""
        old = job_or_404(job_id)
        body = body or m.RerunRequest()
        if not old.audio_path.exists():
            shown = shown_path(old.audio_path) if is_device(request) else old.audio_path
            raise HTTPException(409, f"input {shown} no longer exists")
        if not input_allowed(old.audio_path, anywhere=not is_device(request)):
            raise HTTPException(409, "the input is not an audio file in the engine's audio folders "
                                     "(uploads, captures, eval)")
        job = jobs.submit(old.audio_path, old.profile, audio_id=old.audio_id, title=old.title, params=old.params,
                          allow_heavy=body.allow_heavy, cold=set(body.cold), previous_run_id=old.id,
                          device_name=old.device_name)
        return job_model(job)

    @app.post("/v1/jobs/upload", response_model=m.Job, status_code=202, operation_id="createJobFromUpload",
              tags=["jobs"], dependencies=[Depends(auth)])
    def create_job_from_upload(request: Request, file: UploadFile = File(...), profile: str = Form("orchestra-with-soloist"),
                               title: str | None = Form(None, max_length=200), render_audio: bool = Form(True),
                               lineup: m.Lineup | None = Form(None), difficulty: m.Difficulty = Form("faithful"),
                               key: str | None = Form(None), transpose: int | None = Form(None, ge=-11, le=11),
                               seat: m.Seat | None = Form(None), reads: m.Reads | None = Form(None),
                               lead: m.Lead = Form("lineup")) -> m.Job:
        """Upload audio and start a job in one request (same as uploadAudio followed by createJob)."""
        ref = store_upload(file)
        return create_job(m.JobCreate(audio_id=ref.audio_id, profile=profile, title=title, render_audio=render_audio,
                                      lineup=lineup, difficulty=difficulty, key=key, transpose=transpose, seat=seat,
                                      reads=reads, lead=lead), request)

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

    @app.patch("/v1/runs/{job_id}", response_model=m.Job, operation_id="updateRun", tags=["jobs"],
               dependencies=[Depends(auth)],
               responses={404: {"description": "unknown run"}, 409: {"description": "run is queued or running"}})
    def update_run(job_id: str, body: m.RunUpdate) -> m.Job:
        """Rename a finished score: the title in its manifest, Composition, the score's and parts' MusicXML and
        the talking score. Rendered files (PDF, braille, MIDI, audio) keep the title they were made with."""
        title = body.title.strip()
        if not title:
            raise HTTPException(422, "title must not be blank")
        result = jobs.rename(job_id, title)
        if result == "unknown":
            raise HTTPException(404, f"no run {job_id}")
        if result == "active":
            raise HTTPException(409, f"run {job_id} is still queued or running")
        return job_model(job_or_404(job_id))

    @app.get("/v1/jobs/{job_id}/events", operation_id="streamJobEvents", tags=["jobs"], dependencies=[Depends(auth)],
             response_class=StreamingResponse,
             responses={200: {"description": "Server-Sent Events; each `data:` line is a JobEvent",
                              "content": {"text/event-stream": {"schema": m.JobEvent.model_json_schema(
                                  ref_template="#/components/schemas/{model}")}}}})
    def stream_events(job_id: str, after: int = Query(-1, description="resume after this event id"),
                      last_event_id: str | None = Header(None)) -> StreamingResponse:
        job = job_or_404(job_id)
        start = int(last_event_id) if last_event_id and last_event_id.lstrip("-").isdigit() else after

        async def gen():
            last = start
            while True:
                batch = await anyio.to_thread.run_sync(job.events_after, last, HEARTBEAT_S, limiter=stream_waiters)
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
    def get_manifest(job_id: str, request: Request):
        """What ran: profile, parameters, input, stages. Paired devices get paths relative to the data folder,
        and no git or host details."""
        p = jobs.run_dir(job_or_404(job_id).id) / "manifest.json"
        if not p.exists():
            raise HTTPException(404, "manifest not written yet")
        manifest = json.loads(p.read_text())
        return JSONResponse(device_manifest(manifest) if is_device(request) else manifest)

    @app.get("/v1/jobs/{job_id}/artifacts", response_model=list[m.Artifact], operation_id="listJobArtifacts",
             tags=["results"], dependencies=[Depends(auth)])
    def list_artifacts(job_id: str) -> list[m.Artifact]:
        job = job_or_404(job_id)
        d = jobs.run_dir(job.id) / "outputs"
        return [m.Artifact(name=n, bytes=(d / n).stat().st_size, media_type=media_type(n),
                           url=f"/v1/jobs/{job.id}/artifacts/{n}") for n in outputs_of(job)]

    @app.get("/v1/jobs/{job_id}/artifacts/{name:path}", operation_id="getJobArtifact", tags=["results"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_artifact(job_id: str, name: str, request: Request):
        if name == "manifest.json" and is_device(request):
            return get_manifest(job_id, request)
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

    def part_file(job_id: str, part: str, suffix: str) -> str:
        """Output name of one part's file: part is its 1-based number in score order or its name."""
        d = jobs.run_dir(job_or_404(job_id).id) / "outputs" / "parts"
        files = sorted(d.glob(f"*{suffix}")) if d.is_dir() else []
        want = part.strip().lower()
        for f in files:
            num, _, name = f.name[: -len(suffix)].partition("-")
            if want == num.lstrip("0") or want == num or want == name.lower() or want == name.replace("-", " ").lower():
                return f"parts/{f.name}"
        raise HTTPException(404, f"no part {part!r}; parts are {[f.name[:-len(suffix)] for f in files]}")

    @app.get("/v1/jobs/{job_id}/braille", operation_id="getBraille", tags=["results"], dependencies=[Depends(auth)],
             response_class=FileResponse,
             responses={200: {"description": "Braille music in North American Braille ASCII (.brf, 40 cells per line, "
                                             "25 lines per page)",
                              "content": {"text/plain": {"schema": {"type": "string"}}}}})
    def get_braille(job_id: str, part: str | None = Query(None, description="part number (1-based, score order) or "
                                                                             "name, e.g. 2 or Solo Cornet; omit for the score")):
        """Braille music (BRF) of the score or of one part, transcribed by music21."""
        return output_file(job_id, part_file(job_id, part, ".brf") if part else "brass-band.brf")

    @app.get("/v1/jobs/{job_id}/talking-score", operation_id="getTalkingScore", tags=["results"],
             dependencies=[Depends(auth)],
             responses={200: {"description": "Talking score (docs/accessibility/talking-score-spec.md): HTML with a "
                                             "heading per part and bar, plain text, or the TalkingScore JSON",
                              "content": {"text/html": {"schema": {"type": "string"}},
                                          "text/plain": {"schema": {"type": "string"}},
                                          "application/json": {"schema": {"type": "object"}}}}})
    def get_talking_score(job_id: str,
                          format: str = Query("html", pattern="^(html|text|json)$"),
                          lang: str = Query("en", pattern="^(en|nb)$"),
                          part: str | None = Query(None, description="part number (1-based) or name; omit for all parts"),
                          pitch_mode: str | None = Query(None, pattern="^(written|concert)$",
                                                         description="default: written for one part, concert for the score"),
                          verbosity: str = Query("standard", pattern="^(brief|standard|full)$")):
        """Talking score of the whole score or one part, rendered from the job's talking-score.json."""
        from fastapi.responses import HTMLResponse, PlainTextResponse

        from . import talking_score as T

        p = jobs.run_dir(job_or_404(job_id).id) / "outputs" / "talking-score.json"
        if not p.exists():
            raise HTTPException(404, f"no talking score for job {job_id}")
        doc = json.loads(p.read_text())
        parts = None
        if part:
            names = [x["name"].lower() for x in doc["parts"]]
            want = part.strip().lower()
            if want.isdigit() and 1 <= int(want) <= len(names):
                parts = [int(want) - 1]
            elif want in names:
                parts = [names.index(want)]
            else:
                raise HTTPException(404, f"no part {part!r}; parts are {[x['name'] for x in doc['parts']]}")
        if format == "json":
            if parts is not None:
                doc = {**doc, "parts": [doc["parts"][parts[0]]]}
            return JSONResponse(doc)
        settings = T.Settings(lang=lang, verbosity=verbosity,
                              pitch_mode=pitch_mode or ("written" if parts is not None else "concert"))
        if format == "html":
            return HTMLResponse(T.to_html(doc, settings, parts))
        return PlainTextResponse(T.to_text(doc, settings, parts))

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
    def suite_history(request: Request, suite: str | None = Query(None, description="only results of this suite"),
                      limit: int = Query(1000, ge=1, le=10000)) -> list[m.SuiteHistoryEntry]:
        """Every stored suite result, newest first (from `brasscribe bench` and runSuite)."""
        rows = history.entries(settings, suite, limit)
        if is_device(request):
            rows = [{**r, "manifest": shown_path(r["manifest"])} for r in rows]
        return [m.SuiteHistoryEntry(**r) for r in rows]

    # ------------------------------------------------------------ inspection

    def file_ref(path: Path, name: str, url: str, sha256: str | None = None) -> m.FileRef:
        return m.FileRef(name=name, bytes=path.stat().st_size if path.exists() else 0, media_type=media_type(name),
                         url=url, sha256=sha256)

    def safe_file(root: Path, rel: str) -> Path:
        if not valid_relpath(rel):
            raise HTTPException(404, f"{rel} not found")
        p = (root / rel).resolve()
        if not inspection.inside(root, p) or p == root.resolve() or not p.is_file():
            raise HTTPException(404, f"{rel} not found")
        return p

    @app.get("/v1/jobs/{job_id}/input", operation_id="getJobInput", tags=["inspection"], dependencies=[Depends(auth)],
             response_class=FileResponse, responses={200: {"content": {"audio/wav": {}}}})
    def get_input(job_id: str, request: Request):
        """The job's original input audio (for A/B listening)."""
        job = job_or_404(job_id)
        if not input_allowed(job.audio_path, anywhere=not is_device(request)):
            raise HTTPException(404, "input audio no longer exists, or is not in the engine's audio folders")
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
                queue_wait_s=st.get("queue_wait_s"), run_s=st.get("run_s"), device=st.get("device"),
                files=[file_ref(d / f, f, f"/v1/jobs/{job.id}/stages/{name}/files/{f}", h) for f, h in files.items()]))
        return out

    @app.get("/v1/jobs/{job_id}/evidence", response_model=m.Evidence, operation_id="getJobEvidence", tags=["results"],
             dependencies=[Depends(auth)])
    def get_evidence(job_id: str) -> m.Evidence:
        """Per uncertain note: its confidence and the pitch each transcriber heard, for the apps' Check the notes."""
        from .evidence import evidence

        return m.Evidence(**evidence(jobs.run_dir(job_or_404(job_id).id)))

    @app.get("/v1/jobs/{job_id}/stages/{stage}/files/{name:path}", operation_id="getStageFile", tags=["inspection"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_stage_file(job_id: str, stage: str, name: str):
        job = job_or_404(job_id)
        if not valid_id(stage) or stage not in job.stages:
            raise HTTPException(404, f"no stage {stage} in job {job_id}")
        p = safe_file(jobs.run_dir(job.id) / "stages" / stage, name)
        return FileResponse(p, media_type=media_type(name), filename=p.name)

    @app.get("/v1/references", response_model=list[m.Reference], operation_id="listReferences", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_references() -> list[m.Reference]:
        """Reference outputs under <data>/golden (read only)."""
        root = settings.golden_dir
        out = []
        for d in sorted(p for p in root.iterdir() if valid_id(p.name) and p.is_dir()) if root.is_dir() else []:
            out.append(m.Reference(name=d.name, files=[
                file_ref(f, f.name, f"/v1/references/{d.name}/files/{f.name}") for f in sorted(d.iterdir()) if f.is_file()]))
        return out

    @app.get("/v1/references/{name}/files/{file}", operation_id="getReferenceFile", tags=["inspection"],
             dependencies=[Depends(auth)], response_class=FileResponse,
             responses={200: {"content": {"application/octet-stream": {}}}})
    def get_reference_file(name: str, file: str):
        if not valid_id(name) or not (settings.golden_dir / name).is_dir():
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
        if reference and not (valid_id(reference) and (settings.golden_dir / reference).is_dir()):
            raise HTTPException(404, f"no reference {reference}")
        other = settings.golden_dir / reference if reference else jobs.run_dir(job_or_404(job).id) / "outputs"
        for d in (this, other):
            if not (d / "composition.json").exists() or not (d / "brass-band.musicxml").exists():
                raise HTTPException(404, f"no score output in {d.name}")
        return m.Comparison(**compare(this, other).to_dict())

    def roundtrip_file(job_id: str) -> Path:
        return jobs.run_dir(job_or_404(job_id).id) / "roundtrip.json"

    def roundtrip_model(r: dict, request: Request) -> m.Roundtrip:
        if is_device(request) and r.get("musescore"):
            r = {**r, "musescore": Path(r["musescore"]).name}
        return m.Roundtrip(**r)

    @app.get("/v1/jobs/{job_id}/roundtrip", response_model=m.Roundtrip, operation_id="getRoundtrip",
             tags=["inspection"], dependencies=[Depends(auth)])
    def get_roundtrip(job_id: str, request: Request) -> m.Roundtrip:
        """Stored MuseScore round-trip result, or status not_run (start it with runRoundtrip)."""
        p = roundtrip_file(job_id)
        return roundtrip_model(json.loads(p.read_text()), request) if p.exists() else m.Roundtrip(status="not_run")

    @app.post("/v1/jobs/{job_id}/roundtrip", response_model=m.Roundtrip, operation_id="runRoundtrip",
              tags=["inspection"], dependencies=[Depends(auth)])
    def run_roundtrip(job_id: str, request: Request) -> m.Roundtrip:
        """Re-export the job's MusicXML through MuseScore and compare every part's sounding pitches (takes seconds)."""
        outputs = jobs.run_dir(job_or_404(job_id).id) / "outputs"
        if not (outputs / "brass-band.musicxml").exists():
            raise HTTPException(404, "job has no MusicXML output")
        r = inspection.roundtrip(outputs)
        if r["status"] != "not_run":
            roundtrip_file(job_id).write_text(json.dumps(r, indent=1))
        return roundtrip_model(r, request)

    @app.get("/v1/jobs/{job_id}/part-sources", response_model=m.PartSources, operation_id="getPartSources",
             tags=["results"], dependencies=[Depends(auth)])
    def get_part_sources(job_id: str) -> m.PartSources:
        """Where each part comes from: the player's own recording, the recording, or arranged from the harmony."""
        from brasscribe_music.arranger import part_sources
        from brasscribe_music.score_model import Composition

        comp = jobs.run_dir(job_or_404(job_id).id) / "outputs" / "composition.json"
        if not comp.exists():
            raise HTTPException(404, "job has no Composition output")
        return m.PartSources(parts=part_sources(Composition.from_json(comp)))

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
    def list_sources(request: Request) -> list[m.Source]:
        """Recordings that can start a job without an upload: captures and eval-set items (createJob source_id).
        Paired devices get paths relative to the data folder."""
        found = inspection.sources(settings)
        return [m.Source(**{**x, "path": shown_path(x["path"])} if is_device(request) else x) for x in found]

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
    def list_datasets(request: Request) -> list[m.Dataset]:
        """Eval sets under <data>/eval: size, items, licence, cached model outputs and how to build a missing set.
        Paired devices get paths relative to the data folder."""
        found = inspection.datasets(settings)
        return [m.Dataset(**{**d, "path": shown_path(d["path"])} if is_device(request) else d) for d in found]

    @app.get("/v1/parity", response_model=list[m.Manifest], operation_id="listParityReports", tags=["inspection"],
             dependencies=[Depends(auth)])
    def list_parity() -> list[dict]:
        """Model-conversion parity reports as written (every *.json in BRASSCRIBE_PARITY_REPORTS), plus `_file`."""
        return history.reports(settings.parity_reports_dir)

    @app.get("/v1/conformance", response_model=list[m.Manifest], operation_id="listConformanceReports",
             tags=["inspection"], dependencies=[Depends(auth)])
    def list_conformance(all: bool = Query(False, description="every JSON file of the run (large: each case's "
                                                                  "outputs), not only the summary reports")) -> list[dict]:
        """Rust-core conformance summary: every report.json in BRASSCRIBE_CONFORMANCE_REPORTS as written, plus `_file`.

        An empty list means no report yet (run `brasscribe_conformance.run`, or runConformance)."""
        root = settings.conformance_reports_dir
        return history.reports(root) if all else history.reports(root, "report.json")

    @app.post("/v1/conformance/run", response_model=m.ConformanceRun, status_code=202, operation_id="runConformance",
              tags=["inspection"], dependencies=[Depends(auth)],
              responses={409: {"description": "a run is already in progress"},
                         503: {"description": "core/conformance is not in this checkout"}})
    def run_conformance() -> m.ConformanceRun:
        """Start the Rust-core conformance suite in the background (no MuseScore); poll getConformanceRun."""
        if not conformance_runner.available:
            raise HTTPException(503, "core/conformance is not in this checkout")
        if not conformance_runner.start():
            raise HTTPException(409, "a conformance run is already in progress")
        return m.ConformanceRun(**conformance_runner.snapshot())

    @app.get("/v1/conformance/run", response_model=m.ConformanceRun, operation_id="getConformanceRun",
             tags=["inspection"], dependencies=[Depends(auth)])
    def get_conformance_run() -> m.ConformanceRun:
        """State of the latest conformance run started by this server, with the last lines of its log."""
        return m.ConformanceRun(**conformance_runner.snapshot())

    band = settings.band_sounds_dir
    if band is not None:
        # Before "/": the first matching mount wins.
        if all((band / f).is_file() for f in BAND_SOUND_FILES):
            app.mount("/assets/band", CachedStaticFiles(directory=band, cache_control=BAND_SOUNDS_CACHE),
                      name="band-sounds")
        else:
            print(f"band sounds: {band} has no {' and '.join(BAND_SOUND_FILES)}; Studio plays General MIDI sounds",
                  file=sys.stderr, flush=True)
    if STATIC.is_dir():
        app.mount("/", CachedStaticFiles(directory=STATIC, html=True, cache_control=STUDIO_CACHE), name="studio")
    return app
