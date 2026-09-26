"""API models. Field names are the wire contract for Studio and the native Play apps."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
Lineup = Literal["full", "minimal"]
Difficulty = Literal["faithful", "standard", "easier"]
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
    """Exactly one of audio_id (an upload), source_id (from listSources) or path (a file inside the data directory)."""

    audio_id: str | None = None
    source_id: str | None = None
    path: str | None = Field(None, description="audio file path; must lie inside the engine's data directory")
    profile: str = "orchestra-with-soloist"
    title: str | None = None
    render_audio: bool = Field(True, description="also render an MP3 of the score")
    allow_heavy: bool = Field(True, description="allow heavy models to run on cache misses")
    lineup: Lineup | None = Field(None, description="full: the 18-part brass band; minimal: the 8-part minimal band; "
                                                     "default: the profile's (minimal for solo, full otherwise)")
    muscriptor: bool = Field(True, description="solo profile: confirm SwiftF0 with MuScriptor; false puts Basic Pitch "
                                               "in its place, as the apps do on device")
    difficulty: Difficulty = Field("faithful", description="faithful keeps every transcribed note; standard and "
                                                           "easier simplify rhythms and ranges")
    key: str | None = Field(None, description="target concert key: a tonic (Bb, F#, Eb, Am) or FIFTHS[:MODE] "
                                              "(-2, -2:minor); the arrangement is transposed to it")
    transpose: int | None = Field(None, ge=-11, le=11, description="transpose the arrangement by this many semitones "
                                                                  "(instead of key)")


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
    previous_run_id: str | None = Field(None, description="the job this one re-runs, if any")
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
    status: Literal["pass", "regressed", "improved", "missing", "skipped", "new"]


class SuiteResult(BaseModel):
    suite: str
    status: Literal["pass", "fail", "skipped", "error"]
    reason: str | None = None
    seconds: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    skipped_parts: list[str] = Field(default_factory=list, description="eval sets (metric prefixes) without data")


class BenchRun(BaseModel):
    id: str
    created: str
    target: str = Field(description="suite or group that was run")
    mode: Literal["cached", "live"]
    passed: bool
    git_sha: str | None = None
    device: str | None = None
    suites: list[SuiteResult]


class SuiteHistoryEntry(BaseModel):
    time: float = Field(description="unix seconds")
    run_id: str
    target: str
    suite: str
    status: Literal["pass", "fail", "skipped", "error"]
    reason: str | None = None
    metrics: dict[str, float]
    checks: list[Check]
    manifest: str | None = Field(None, description="history file this entry came from")
    git_sha: str | None = None
    device: str | None = None


class RerunRequest(BaseModel):
    allow_heavy: bool = True
    cold: list[str] = Field(default_factory=list, description="stages or kinds to run even on a cache hit, or 'all'")


class RunUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="new title for the score")


# ---------------------------------------------------------------- inspection


class FileRef(BaseModel):
    name: str
    bytes: int
    media_type: str
    url: str
    sha256: str | None = None


class StageArtifacts(BaseModel):
    stage: str
    kind: str | None = None
    status: str
    key: str | None = None
    seconds: float | None = None
    device: str | None = None
    files: list[FileRef]


class Reference(BaseModel):
    name: str
    files: list[FileRef]


class ModelInfo(BaseModel):
    model: str = Field(description="adapter id, e.g. basic-pitch")
    name: str = Field(description="display name, e.g. Basic Pitch")


class ModelHeard(ModelInfo):
    pitch: int | None = Field(None, description="concert MIDI pitch this model heard at the note's onset; null: no note")
    agrees: bool


class NoteEvidence(BaseModel):
    voice: str
    start: int = Field(description="Composition tick of the note")
    pitch: int = Field(description="concert MIDI pitch Brasscribe wrote")
    confidence: float
    onset_s: float | None = None
    models: list[ModelHeard]


class Evidence(BaseModel):
    """What each transcriber heard at the notes Brasscribe is unsure about (confidence below 0.7)."""

    models: list[ModelInfo]
    notes: list[NoteEvidence]


class PartComparison(BaseModel):
    name: str
    notes: int
    reference_notes: int
    identical: bool


class Comparison(BaseModel):
    composition_identical: bool
    musicxml_identical: bool
    ok: bool
    parts: list[PartComparison]
    parts_identical: int
    parts_total: int
    notes_identical: int
    notes_total: int
    extra_files: dict[str, bool] = Field(default_factory=dict, description="parts/*.musicxml and separation-check.json "
                                                                            "the reference has: identical?")


class RoundtripPart(BaseModel):
    name: str
    sound: str | None = None
    notes: int
    match: bool | None = Field(None, description="null for unpitched parts, which are not compared")


class Roundtrip(BaseModel):
    status: Literal["pass", "fail", "not_run"]
    musescore: str | None = None
    parts: int | None = None
    notes_in: int | None = Field(None, description="pitched notes in the arrangement")
    notes_out: int | None = Field(None, description="pitched notes read back from MuseScore's export")
    detail: str | None = None
    part_results: list[RoundtripPart] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    part: str | None = None
    bar: int | None = None
    beat: float | None = None
    tick: int | None = None
    kind: Literal["range", "crossing", "other"]
    severity: Literal["warning", "error"]
    message: str


class ModelFile(BaseModel):
    name: str
    sha256: str | None = None
    revision: str | None = None
    bytes: int | None = None
    licence: str | None = None
    present: bool


class AdapterInfo(BaseModel):
    name: str
    version: str | None = None
    fingerprint: str
    heavy: bool
    device: str
    licence: str | None = None
    models: list[ModelFile]


class Dataset(BaseModel):
    name: str
    path: str
    licence: str | None = None
    source_url: str | None = None
    bytes: int
    files: int
    items: int
    present: bool
    cached_outputs: list[str] = Field(description="model output files present for every item (e.g. muscriptor-medium.mid)")
    download: str | None = Field(None, description="how to build the set when it is missing")


class Source(BaseModel):
    kind: Literal["capture", "dataset"]
    id: str
    name: str
    path: str
    dataset: str | None = None
    duration_s: float | None = None


Manifest = dict[str, Any]
