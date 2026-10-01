"""API models. Field names are the wire contract for Studio and the native Play apps."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
Lineup = Literal["full", "minimal", "quartet"]
Difficulty = Literal["faithful", "standard", "easier"]
# The player's seat: one of the contest band's parts (brasscribe_music.instruments.SEATS).
Seat = Literal["soprano-cornet", "solo-cornet", "repiano-cornet", "2nd-cornet", "3rd-cornet", "flugelhorn",
               "solo-horn", "1st-horn", "2nd-horn", "1st-baritone", "2nd-baritone", "1st-trombone",
               "2nd-trombone", "bass-trombone", "euphonium", "eb-bass", "bb-bass", "percussion", "trumpet"]
Reads = Literal["treble", "bass"]
Lead = Literal["lineup", "seat"]
# The tab profile's options (tab.py; bass_tab.py for the bass and the bass-tab profile id).
FrettedInstrument = Literal["bass-4", "bass-5", "bass-6", "guitar-6", "guitar-7", "guitar-8", "ukulele", "ukulele-baritone",
                            "mandolin"]
NotationClef = Literal["treble", "treble-8vb", "bass-8vb"]
FingeringStyle = Literal["as-played", "open-position", "lead"]
Recording = Literal["song", "instrument"]
Octave = Literal["auto", "0", "-12", "+12"]
TabLayout = Literal["tab", "tab-and-notation", "notation"]
StageStatus = Literal["pending", "started", "cached", "imported", "ran", "failed", "skipped"]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    build: str | None = Field(None, description="which build is running: the commit and workspace stamp of an "
                                                "installed engine, the commit of a checkout; null when unknown")
    device: str = Field(description="accelerator torch adapters use on this host: cuda, mps or cpu")
    auth_required: bool = Field(description="whether this client must send a bearer token")
    server_id: str = Field(description="stable id of this engine: kept across restarts and address or port changes, "
                                       "new only after `brasscribe devices reset`. Match a rediscovered engine to "
                                       "its stored credential by this id, not by address. An identifier, not proof "
                                       "of identity.")
    server_name: str = Field(description="display name, e.g. 'Brasscribe on studio-mac'")


class PairRequest(BaseModel):
    code: str = Field(description="pairing code shown by the engine (brasscribe serve --lan)")
    device_name: str | None = None
    platform: str | None = Field(None, description="ios, macos, android or windows; shown in the device list")


class PairResponse(BaseModel):
    """Every value is a string: older Apple clients decode this object as [String: String]."""

    token: str = Field(description="this device's own credential: send as 'Authorization: Bearer <token>'. It stays "
                                   "valid across engine restarts until revoked; keep it in the platform keystore")
    device_id: str = Field(description="this device's id in the engine's device list")
    server_id: str = Field(description="the engine's stable id (as in /v1/health); store it with the token")
    server_name: str


class DeviceInfo(BaseModel):
    device_id: str
    name: str
    platform: str
    paired_at: str = Field(description="ISO 8601, UTC")
    last_seen: str = Field(description="ISO 8601, UTC; updated on every request the device makes")
    rotated_at: str | None = None
    online: bool = Field(description="seen in the last 60 seconds (Play apps send GET /v1/devices/me every "
                                            "20 s while open)")


class DeviceSelf(DeviceInfo):
    server_id: str
    rotate_after: str = Field(description="ISO 8601; rotate the token (POST /v1/devices/me/rotate) after this time")
    expires_if_idle_after: str = Field(description="ISO 8601; the credential is forgotten if unused until then")


class RotateResponse(BaseModel):
    token: str = Field(description="the new token; store it before using it. The token used for this request "
                                   "keeps working until this one is first used (at most 30 days), so retrying after "
                                   "a lost response is safe")
    device_id: str


class PairingOpen(BaseModel):
    ttl_s: float | None = Field(600, ge=30, le=86400,
                                description="seconds the code stays valid; null keeps it open until closed")
    single_use: bool = True
    extend: bool = Field(False, description="keep the current code and push its expiry out by ttl_s")


class EngineStatus(BaseModel):
    """What the desktop helper shows about the running engine; polled every few seconds."""

    server_id: str
    server_name: str = Field(description="'Brasscribe on <computer name>'")
    version: str
    online_devices: int = Field(description="paired devices seen in the last 60 seconds")
    paired_devices: int
    pairing_open: bool = Field(description="whether a pairing code is accepted right now")
    jobs_running: int
    jobs_queued: int


class PairingState(BaseModel):
    """What the computer shows to pair a phone: the code, and the payload a QR code encodes."""

    open: bool
    code: str | None = None
    expires_at: str | None = Field(None, description="ISO 8601; null while open with no expiry")
    single_use: bool
    server_id: str
    server_name: str
    hosts: list[str] = Field(description="ip:port addresses the engine is reachable on")
    fingerprint: str | None = Field(None, description="SHA-256 of the TLS key (SPKI), base64url; null while the "
                                                       "engine serves plain HTTP")
    uri: str = Field(description="pairing payload: brasscribe://pair?v=1&id=..&name=..&h=..&code=..[&fp=..]")
    locked_until: str | None = Field(None, description="ISO 8601; set while too many wrong codes have locked "
                                                        "pairing, so the computer can say so. The code stays the same")


class PairRequestCreate(BaseModel):
    device_name: str | None = None
    platform: str | None = None


class PairRequestInfo(BaseModel):
    request_id: str
    name: str
    platform: str
    match_code: str = Field(description="four digits shown on both screens so the owner can tell which device asks")
    created_at: str
    status: Literal["pending", "approved", "denied"]
    name_in_use: bool = Field(False, description="a device already paired with this engine has the same name "
                                                 "(ignoring case): the owner can't tell the two apart by name, so "
                                                 "the apps can suggest another one")


class PairRequestResult(BaseModel):
    status: Literal["pending", "approved", "denied"]
    token: str | None = Field(None, description="set once, on the first poll after approval")
    device_id: str | None = None
    server_id: str | None = None
    server_name: str | None = None


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
    """Exactly one of audio_id (an upload), source_id (from listSources) or path (an audio file in the data directory)."""

    audio_id: str | None = None
    source_id: str | None = None
    path: str | None = Field(None, description="audio file under uploads/, captures/ or eval/, relative to the engine's "
                                               "data directory ('/'-separated); not for paired devices")
    profile: str = "orchestra-with-soloist"
    title: str | None = Field(None, max_length=200)
    render_audio: bool = Field(True, description="also render an MP3 of the score")
    allow_heavy: bool = Field(True, description="allow heavy models to run on cache misses")
    lineup: Lineup | None = Field(None, description="full: the 18-part brass band; minimal: the 8-part minimal band; "
                                                     "quartet: 1st Cornet, 2nd Cornet, Tenor Horn and Euphonium, one "
                                                     "player each (not for the solo profile: it needs a recording of "
                                                     "the whole group); default: the profile's (minimal for solo, "
                                                     "full otherwise)")
    muscriptor: bool = Field(True, description="solo and brass-band profiles: use MuScriptor; false puts Basic Pitch "
                                               "in its place, as the apps do on device")
    difficulty: Difficulty = Field("faithful", description="faithful keeps every transcribed note; standard and "
                                                           "easier simplify rhythms and ranges")
    key: str | None = Field(None, description="target concert key: a tonic (Bb, F#, Eb, Am) or FIFTHS[:MODE] "
                                              "(-2, -2:minor); the arrangement is transposed to it")
    transpose: int | None = Field(None, ge=-11, le=11, description="transpose the arrangement by this many semitones "
                                                                  "(instead of key)")
    seat: Seat | None = Field(None, description="the player's seat. A solo take is written for it: one part, the "
                                                "seat's, in its range and in the octave played. A band take's notes "
                                                "do not change; the seat names the player's part. Default: none")
    reads: Reads | None = Field(None, description="the clef the seat's part is written in: bass is at concert pitch "
                                                  "(offered for baritone, euphonium, trombones and basses); default: "
                                                  "the brass-band part's own")
    lead: Lead = Field("lineup", description="who plays the tune: lineup keeps it on the lineup's lead (Solo Cornet); "
                                             "seat writes it on the seat's part, for the full and minimal bands only. "
                                             "The solo profile with a seat always uses seat")
    instrument: FrettedInstrument | None = Field(None, description="tab profile: the instrument the tab is written for. "
                                                 "Default: guitar-6. The bass-tab profile takes the basses only; "
                                                 "default: bass-4")
    tuning: str | None = Field(None, description="tab profile: the instrument's tuning, its first when left out. bass-4: "
                                                 "standard, eb-standard, d-standard, drop-d, bead; bass-5: standard, drop-a; "
                                                 "bass-6: standard; guitar-6: standard, eb-standard, d-standard, c-standard, "
                                                 "drop-d, drop-c, drop-b, dadgad, open-g, open-d, open-e; guitar-7: standard, "
                                                 "eb-standard; guitar-8: standard; ukulele: high-g, low-g; ukulele-baritone, "
                                                 "mandolin: standard")
    capo: int | None = Field(None, ge=0, le=12, description="tab profile: the capo's fret; frets in the tab are "
                                                            "counted from it, and the page names it; default: 0, no capo")
    style: FingeringStyle | None = Field(None, description="tab profile: where the line sits on the neck. "
                                                           "as-played: the cheapest playable fingering; open-position: "
                                                           "low frets and open strings; lead: a phrase stays in one "
                                                           "position; default: as-played")
    recording: Recording | None = Field(None, description="tab profile: what was recorded. song: a band or a record, "
                                                          "the instrument is separated from it (a ukulele or mandolin "
                                                          "from the guitar stem, with any guitar in the song); "
                                                          "instrument: the instrument alone, no separation; default: song")
    layout: TabLayout | None = Field(None, description="tab profile: what the page shows. tab: the tab staff alone, "
                                                       "with stems for the rhythm; tab-and-notation: a notation staff "
                                                       "above it; notation: the notation staff alone; default: tab")
    octave: Octave | None = Field(None, description="tab profile: the octave the notes are written in. auto: an "
                                                    "octave lower when they were heard an octave above where the "
                                                    "instrument plays (a guitar: also an octave higher when heard "
                                                    "below it); 0, -12, +12: the player's choice, in semitones from "
                                                    "what was heard; default: auto")


class PartSources(BaseModel):
    """Where each part of the job's score comes from, in score order (derived from the Composition)."""

    parts: dict[str, Literal["your-recording", "recording", "arranged", "empty"]] = Field(
        description="your-recording: a solo take's own line; recording: a line heard in the recording (the tune, the "
                    "bass line, the countermelody, the drums); arranged: voiced from the band's harmony; empty: "
                    "nothing to play in this arrangement (no drums in the recording, no climax for the soprano)")


class StageState(BaseModel):
    name: str
    kind: str | None = None
    status: StageStatus
    seconds: float | None = Field(None, description="wall clock, including any wait for the GPU mutex")
    queue_wait_s: float | None = Field(None, description="of `seconds`, time spent waiting for the machine-wide GPU mutex")
    run_s: float | None = Field(None, description="of `seconds`, time the stage itself took (seconds - queue_wait_s)")
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
    device_name: str | None = Field(None, description="name of the paired device that started the job; null when "
                                    "started on the engine's own computer (Studio, loopback) or with a static token")
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
    queue_wait_s: float | None = Field(None, description="of `seconds`, time spent waiting for the machine-wide GPU mutex")
    run_s: float | None = Field(None, description="of `seconds`, time the stage itself took (seconds - queue_wait_s)")
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


# ---------------------------------------------------------------- tablature


class TabPosition(BaseModel):
    string: int = Field(description="1 is the highest line of the tab")
    fret: int = Field(description="counted from the capo; 0 is the open string")


class TabNote(BaseModel):
    """One note of the tab: when it sounds, what was heard, and where it is played."""

    pitch: int = Field(description="concert MIDI pitch, as written in the tab (after octave_shift)")
    start: int = Field(description="ticks from the first downbeat")
    dur: int = Field(description="written duration in ticks")
    confidence: float = Field(1.0, description="0 to 1. Below 0.4 the note is one to check (the tab marks it \"?\"): "
                                               "the second transcriber did not hear it at this pitch, or, where "
                                               "there is no second opinion, it was heard faintly")
    onset_s: float | None = None
    offset_s: float | None = None
    string: int | None = Field(description="null: the note has no place on the instrument")
    fret: int | None = None
    alternatives: list[TabPosition] = Field(description="the other places that sound this pitch, cheapest first")
    out_of_range: bool = Field(description="no string of the instrument sounds this pitch; the usual cause is "
                                           "another tuning or instrument than the player's")
    pinned: bool = False
    octave_moved: bool = Field(False, description="written an octave below where Basic Pitch heard it, where the second "
                                                  "transcriber heard it. Its confidence is that of any note both heard: in "
                                                  "the benchmark four in five of these are right, so it gets no \"?\"")


class TabString(BaseModel):
    open_pitch: int = Field(description="MIDI pitch of the open string, without the capo")
    first_fret: int = Field(0, description="where a short string starts (a banjo's fifth string); 0: at the nut")


class TabTuning(BaseModel):
    name: str = Field(description="display name, e.g. Drop D")
    strings: list[TabString] = Field(description="string 1 first")


class TabInstrument(BaseModel):
    name: str
    tuning: TabTuning
    frets: int
    scale_length_mm: float
    capo: int = 0
    notation: NotationClef | None = Field(None, description="the clef of the instrument's notation staff: treble (ukulele, "
                                                            "mandolin), treble-8vb (guitar and baritone ukulele, written an "
                                                            "octave above their sound), bass-8vb (bass)")


class TabViolation(BaseModel):
    """A hard playability violation (core/target-fretted/README.md, Playability check); the other fields
    depend on `kind` and name notes by their index in `notes`."""

    model_config = ConfigDict(extra="allow")
    kind: str = Field(description="shared-string, span-too-wide, fret-out-of-range, wrong-pitch, pin-not-honoured, "
                                  "no-string, technique-string, technique-reach, bend-on-open-string or ring-cut")


class TuningFit(BaseModel):
    """How well one tuning of the instrument fits the notes."""

    preset: str = Field(description="<instrument>-<tuning>, e.g. bass-4-drop-d")
    tuning: str = Field(description="display name, e.g. Drop D")
    out_of_range: int = Field(description="notes no string can sound")
    low_string_fits: bool = Field(description="the lowest note is exactly the lowest open string")
    open_notes: int = Field(description="notes an open string can play")
    high_frets: int = Field(description="notes that can only be played above the 12th fret")
    distance: int = Field(description="semitones from the standard tuning, summed over the strings")


class TabKey(BaseModel):
    name: str = Field(description="tonic and mode, e.g. G or Em")
    fifths: int
    mode: Literal["major", "minor"]


class TabMeter(BaseModel):
    beats: int
    beat_unit: int = 4


class ReferencePitch(BaseModel):
    cents: float = Field(description="offset of the recording from A = 440, -50 to 50; positive is sharp")
    concentration: float = Field(description="how well the recording agrees on it, 0 to 1")
    retuned: bool = Field(description="the notes were transcribed from the recording retuned to A = 440")


class Tab(BaseModel):
    """The tab profile's result (and bass-tab's): every note with its string and fret, and what the song check shows
    before the tab (tuning, reference pitch, capo, octave, key and tempo)."""

    preset: str = Field(description="the instrument and tuning the tab was made for, e.g. bass-4-standard")
    style: FingeringStyle
    instrument: TabInstrument
    notes: list[TabNote] = Field(description="in time order; violations name notes by their index here")
    violations: list[TabViolation] = Field(description="empty when the tab is playable as written")
    tuning_suggestions: list[TuningFit] = Field(description="the instrument's tunings ranked by fit to the notes, "
                                                            "best first; when the first is not `preset`, the song "
                                                            "sounds like that tuning")
    layout: TabLayout = Field(description="what tab.musicxml (and the PDF made from it) shows")
    adjusted_notes: int = Field(description="notes whose start or length no note value could spell, written at the "
                                            "nearest one that can; in tab.musicxml only, the notes here are unchanged")
    octave_shift: int = Field(description="semitones the whole line was moved after transcription. With octave auto: "
                                          "0, or -12 (or -24) when it was heard an octave above where a bass plays, "
                                          "the same for every instrument, tuning and capo. With a chosen octave: "
                                          "that choice, 0, -12 or 12")
    unplayable_dropped: int = Field(0, description="notes heard that are not in the tab because the instrument cannot "
                                                   "play them with the others: more notes on one onset than it has "
                                                   "strings, a chord no hand spans, or a note below its lowest string "
                                                   "that is the lower octave of a note in the same strum. Always 0 "
                                                   "for a bass line")
    leftovers_dropped: int = Field(0, description="notes Basic Pitch heard that are not in the tab because they were "
                                                  "not played: notes shorter than 0.06 s; in a line, faint overtones of a sounding note and "
                                                  "notes heard very faintly; among a guitar's or a ukulele's chords, overtones above "
                                                  "the 12th fret of the top string. One pitch heard twice on one onset "
                                                  "is one note and is not counted. Always 0 for a bass line, whose "
                                                  "own count is in the job's log")
    octave_notes_moved: int = Field(0, description="single notes written an octave lower than Basic Pitch heard them "
                                                   "(with octave auto): each stood above its neighbours, and the second "
                                                   "transcriber heard it an octave lower")
    octave_source: Literal["auto", "chosen"] = Field(description="auto: the octave check decided octave_shift; chosen: "
                                                                 "the job's octave option did")
    reference_pitch: ReferencePitch | None = Field(description="null when the recording's tuning could not be measured")
    tempo_bpm: float
    key: TabKey
    meter: TabMeter
    ticks_per_beat: int = 24
    beat_times: list[float] = Field(description="seconds of beat 0, 1, 2 ...")
    first_downbeat: int = Field(description="index into beat_times of tick 0; negative when the line starts before "
                                            "the first tracked downbeat (a pickup): tick 0 is then a bar line "
                                            "before beat_times[0]")


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
    queue_wait_s: float | None = Field(None, description="of `seconds`, time spent waiting for the machine-wide GPU mutex")
    run_s: float | None = Field(None, description="of `seconds`, time the stage itself took (seconds - queue_wait_s)")
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


class ConformanceRun(BaseModel):
    status: Literal["idle", "running", "succeeded", "failed"]
    available: bool = Field(description="core/conformance exists in this checkout")
    started: float | None = None
    finished: float | None = None
    exit_code: int | None = Field(None, description="0: every case identical; 1: some case differs")
    command: list[str] = Field(default_factory=list)
    log: str | None = Field(None, description="log file of the run")
    log_tail: str | None = Field(None, description="last lines of the log")


Manifest = dict[str, Any]
