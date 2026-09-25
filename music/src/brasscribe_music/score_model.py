"""Canonical symbolic score: the boundary between transcription and arrangement.

Transcription produces a Composition (what music exists); the arranger reads
only a Composition and decides how a brass band plays it. Everything is at
concert pitch in integer ticks (TICKS_PER_BEAT per beat); seconds are kept
alongside so the score can be aligned back to the recording.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path

from .quantize import TICKS_PER_BEAT


def _plain(o):
    """JSON fallback: numpy scalars become plain numbers, enums their value; anything else is an error."""
    if hasattr(o, "item") and callable(o.item):
        return o.item()
    if isinstance(o, Enum):
        return o.value
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


class Articulation(str, Enum):
    STACCATO = "staccato"  # performed length under half the written length
    FERMATA = "fermata"  # held beyond its written value (phrase ends in free time)


class FreeNotation(str, Enum):
    PROPORTIONAL = "proportional"  # local tempo estimated from the note stream
    TEMPO = "tempo"  # a tempo the user gave for the passage


class VoiceRole(str, Enum):
    MELODY = "melody"
    COUNTERMELODY = "countermelody"
    HARMONY = "harmony"
    BASS = "bass"
    RHYTHM = "rhythm"


@dataclass
class Note:
    pitch: int  # concert MIDI pitch
    start: int  # ticks from the first downbeat (may be negative in a pickup)
    dur: int  # notated duration in ticks
    confidence: float = 1.0
    sources: list[str] = field(default_factory=list)
    onset_s: float | None = None
    offset_s: float | None = None
    performed_dur: int | None = None  # performed length in ticks (offset - onset on the tick map); None = unknown
    articulations: list[Articulation] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.dur

    @staticmethod
    def from_dict(d: dict) -> Note:
        known = {f.name for f in fields(Note)}
        n = Note(**{k: v for k, v in d.items() if k in known})
        n.articulations = [Articulation(a) for a in n.articulations]
        return n


@dataclass
class Voice:
    id: str
    role: VoiceRole
    notes: list[Note] = field(default_factory=list)
    instrument_hint: str | None = None  # what the source instrument seemed to be; never binding
    layer: str | None = None  # textural layer it came from: solo, strings, brass, keys, bass, drums


@dataclass
class Meter:
    tick: int
    beats: int
    beat_unit: int = 4


@dataclass
class KeySig:
    tick: int
    fifths: int
    mode: str = "major"


@dataclass
class Dynamic:
    """A dynamic marking for one textural layer from `tick` on (pp, p, mp, mf, f, ff)."""

    tick: int
    layer: str
    mark: str


@dataclass
class FreeRegion:
    """A passage in free time (ad lib., colla voce): no beat grid was imposed on it.

    Its span is [start, end) in ticks and [start_s, end_s) in seconds. Inside it
    the beat_times are synthetic and evenly spaced at `tempo_bpm`, so the tick
    map stays a plain beat list; positions and lengths there are proportional
    to performed time. `end` is a bar line: the strict grid resumes on it.
    """

    start: int
    end: int
    start_s: float
    end_s: float
    tempo_bpm: float
    notation: FreeNotation = FreeNotation.PROPORTIONAL
    label: str = "ad lib."

    @staticmethod
    def from_dict(d: dict) -> FreeRegion:
        r = FreeRegion(**d)
        r.notation = FreeNotation(r.notation)
        return r


@dataclass
class Composition:
    title: str
    voices: list[Voice]
    meters: list[Meter]
    keys: list[KeySig]
    beat_times: list[float] = field(default_factory=list)  # seconds of beat 0, 1, 2 ... (tempo map)
    first_downbeat: int = 0  # index into beat_times of tick 0
    ticks_per_beat: int = TICKS_PER_BEAT
    free_regions: list[FreeRegion] = field(default_factory=list)
    dynamics: list[Dynamic] = field(default_factory=list)

    def free_region_at(self, tick: int) -> FreeRegion | None:
        return next((r for r in self.free_regions if r.start <= tick < r.end), None)

    def voices_with(self, role: VoiceRole) -> list[Voice]:
        return [v for v in self.voices if v.role == role]

    @property
    def end_tick(self) -> int:
        return max((n.end for v in self.voices for n in v.notes), default=0)

    @property
    def bpm(self) -> float:
        """Median tempo of the strict (gridded) passages."""
        if len(self.beat_times) < 2:
            return 120.0
        tpb = self.ticks_per_beat
        diffs = sorted(b - a for i, (a, b) in enumerate(zip(self.beat_times, self.beat_times[1:]))
                       if self.free_region_at((i - self.first_downbeat) * tpb) is None) or \
            sorted(b - a for a, b in zip(self.beat_times, self.beat_times[1:]))
        return 60.0 / diffs[len(diffs) // 2]

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=1, default=_plain))

    @staticmethod
    def from_json(path: Path) -> Composition:
        d = json.loads(path.read_text())
        voices = [Voice(v["id"], VoiceRole(v["role"]), [Note.from_dict(n) for n in v["notes"]], v.get("instrument_hint"),
                        v.get("layer")) for v in d["voices"]]
        return Composition(d["title"], voices, [Meter(**m) for m in d["meters"]], [KeySig(**k) for k in d["keys"]],
                           d.get("beat_times", []), d.get("first_downbeat", 0), d.get("ticks_per_beat", TICKS_PER_BEAT),
                           [FreeRegion.from_dict(r) for r in d.get("free_regions", [])],
                           [Dynamic(**x) for x in d.get("dynamics", [])])
