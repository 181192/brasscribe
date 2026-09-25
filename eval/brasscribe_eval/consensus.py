"""Note-level consensus across transcription sources.

A source is one (model, stem) note stream, e.g. "basic-pitch/bass" or
"muscriptor/mix". Notes from different sources that share a pitch and start
within ONSET_TOL are clustered into one candidate. Each candidate gets a
confidence from its supporting sources:

    confidence = 1 - prod(1 - precision_s)   over supporting sources s

so agreement between independent models raises confidence, and one reliable
source alone can still carry a note. Candidates below the threshold are kept
as alternatives instead of being discarded.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pretty_midi

ONSET_TOL = 0.10


@dataclass
class Candidate:
    pitch: int
    onsets: list[float] = field(default_factory=list)
    offsets: list[float] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)

    def to_note(self, confidence: float) -> dict:
        return {"pitch": self.pitch, "onset": float(np.median(self.onsets)), "offset": float(np.median(self.offsets)),
                "confidence": round(confidence, 3), "sources": sorted(self.sources)}


def load_sources(midi_paths: dict[str, Path], split_tracks: bool) -> dict[str, list[dict]]:
    """Load MIDI files as sources; with split_tracks each MIDI track (stem) is its own source."""
    out: dict[str, list[dict]] = {}
    for label, path in midi_paths.items():
        pm = pretty_midi.PrettyMIDI(str(path))
        for inst in pm.instruments:
            if inst.is_drum:
                continue
            key = f"{label}/{inst.name}" if split_tracks else label
            out.setdefault(key, []).extend({"pitch": n.pitch, "onset": n.start, "offset": n.end} for n in inst.notes)
    return out


def cluster(sources: dict[str, list[dict]]) -> list[Candidate]:
    events = sorted((n["onset"], n["pitch"], n["offset"], s) for s, notes in sources.items() for n in notes)
    open_by_pitch: dict[int, list[Candidate]] = {}
    done: list[Candidate] = []
    for onset, pitch, offset, src in events:
        bucket = open_by_pitch.setdefault(pitch, [])
        target = None
        for c in bucket:
            if onset - c.onsets[0] <= ONSET_TOL and src not in c.sources:
                target = c
                break
        if target is None:
            target = Candidate(pitch)
            bucket.append(target)
            done.append(target)
        target.onsets.append(onset)
        target.offsets.append(offset)
        target.sources.add(src)
        # Retire candidates that can no longer accept notes.
        open_by_pitch[pitch] = [c for c in bucket if onset - c.onsets[0] <= ONSET_TOL]
    return done


def source_family(source: str) -> str:
    """Stems of one model share a precision estimate unless given explicitly."""
    return source.split("/")[0]


def consensus(sources: dict[str, list[dict]], precision: dict[str, float], threshold: float) -> tuple[list[dict], list[dict]]:
    accepted, alternatives = [], []
    for c in cluster(sources):
        # Stems of one model are not independent (separation bleed duplicates notes),
        # so each model family votes once with its most reliable supporting stem.
        best: dict[str, float] = {}
        for s in c.sources:
            p = precision.get(s, precision.get(source_family(s), 0.3))
            fam = source_family(s)
            best[fam] = max(best.get(fam, 0.0), p)
        miss = 1.0
        for p in best.values():
            miss *= 1.0 - p
        note = c.to_note(1.0 - miss)
        (accepted if note["confidence"] >= threshold else alternatives).append(note)
    accepted.sort(key=lambda n: (n["onset"], n["pitch"]))
    return accepted, alternatives


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("sources", nargs="+", help="label=path.mid")
    ap.add_argument("--precision", type=json.loads, default={}, help='JSON {"label": precision}')
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--split-tracks", action="store_true")
    args = ap.parse_args()
    paths = dict(s.split("=", 1) for s in args.sources)
    notes, alts = consensus(load_sources({k: Path(v) for k, v in paths.items()}, args.split_tracks),
                            args.precision, args.threshold)
    args.output.write_text(json.dumps({"notes": notes, "alternatives": alts}, indent=1))


if __name__ == "__main__":
    main()
