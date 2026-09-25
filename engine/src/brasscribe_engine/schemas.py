"""API models. Field names are the wire contract for Studio and the native Play apps."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
StageStatus = Literal["pending", "started", "cached", "imported", "ran", "failed", "skipped"]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    device: str = Field(description="accelerator torch adapters use on this host: cuda, mps or cpu")
    auth_required: bool = Field(description="whether this client must send a bearer token")


class PairRequest(BaseModel):
    code: str = Field(description="pairing code shown by the engine (brasscribe serve --host 0.0.0.0)")
    device_name: str | None = None


class PairResponse(BaseModel):
    token: str = Field(description="send as 'Authorization: Bearer <token>' on every request")


class ProfileInfo(BaseModel):
    name: str
    pipeline: str
    description: str
    validated: bool = Field(description="checked end to end against a golden output")
    stages: list[str]


class AudioRef(BaseModel):
    audio_id: str
    sha256: str
    filename: str
    bytes: int


class JobCreate(BaseModel):
    audio_id: str
    profile: str = "orchestra-with-soloist"
    title: str | None = None
    render_audio: bool = Field(True, description="also render an MP3 of the score")
    allow_heavy: bool = Field(True, description="allow heavy models to run on cache misses")


class StageState(BaseModel):
    name: str
    kind: str | None = None
    status: StageStatus
    seconds: float | None = None
    device: str | None = None


class Job(BaseModel):
    id: str
    profile: str
    title: str | None = None
    audio_id: str | None = None
    status: JobStatus | Literal["unknown"]
    created: float
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    progress: float = Field(0.0, description="share of stages finished, 0..1")
    stages: list[StageState]
    outputs: list[str] = Field(default_factory=list, description="names fetchable under /v1/jobs/{id}/artifacts/{name}")


class Artifact(BaseModel):
    name: str
    bytes: int
    media_type: str
    url: str


class JobEvent(BaseModel):
    """One Server-Sent Event payload (the `data:` line); `event:` carries `type`."""

    model_config = ConfigDict(extra="allow")
    id: int
    run: str
    type: Literal["job", "stage", "log"]
    time: float
    status: str | None = None
    stage: str | None = None
    kind: str | None = None
    seconds: float | None = None
    device: str | None = None
    fraction: float | None = Field(None, description="share of the job's stages done (stage events)")
    message: str | None = None
    error: str | None = None


# ---------------------------------------------------------------- Composition


class Note(BaseModel):
    model_config = ConfigDict(extra="allow")
    pitch: int = Field(description="concert MIDI pitch")
    start: int = Field(description="ticks from the first downbeat (negative in a pickup)")
    dur: int = Field(description="notated duration in ticks")
    confidence: float = 1.0
    sources: list[str] = Field(default_factory=list)
    onset_s: float | None = None
    offset_s: float | None = None


class Voice(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    role: Literal["melody", "countermelody", "harmony", "bass", "rhythm"]
    notes: list[Note]
    instrument_hint: str | None = None
    layer: str | None = None


class Meter(BaseModel):
    model_config = ConfigDict(extra="allow")
    tick: int
    beats: int
    beat_unit: int = 4


class KeySig(BaseModel):
    model_config = ConfigDict(extra="allow")
    tick: int
    fifths: int
    mode: str = "major"


class Composition(BaseModel):
    """The canonical score (brasscribe_music.score_model.Composition): concert pitch, integer ticks."""

    model_config = ConfigDict(extra="allow")
    title: str
    voices: list[Voice]
    meters: list[Meter]
    keys: list[KeySig]
    beat_times: list[float] = Field(default_factory=list, description="seconds of beat 0, 1, 2 ...")
    first_downbeat: int = 0
    ticks_per_beat: int = 24


# ---------------------------------------------------------------- benchmarks


class SuiteInfo(BaseModel):
    name: str
    description: str
    cpu: bool = Field(description="runs on CPU from cached model outputs")
    requires: list[str] = Field(description="data paths the suite reads, relative to the data directory")


class Check(BaseModel):
    metric: str
    value: float | None
    baseline: float | None
    tolerance: float
    status: Literal["pass", "regressed", "improved", "missing", "new"]


class SuiteResult(BaseModel):
    suite: str
    status: Literal["pass", "fail", "skipped", "error"]
    reason: str | None = None
    seconds: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)


Manifest = dict[str, Any]
