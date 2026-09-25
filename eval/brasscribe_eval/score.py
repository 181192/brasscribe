"""Score transcribed notes against a reference with mir_eval.

Reports instrument-agnostic note metrics (onset-only and onset+offset), octave
errors, and per-part recall so we can see which voices a model loses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

ONSET_TOL = 0.05
LOOSE_TOL = 0.10


def load_notes(path: Path) -> list[dict]:
    if path.suffix in (".mid", ".midi"):
        pm = pretty_midi.PrettyMIDI(str(path))
        return [{"pitch": n.pitch, "onset": n.start, "offset": n.end, "instrument": inst.name or str(inst.program)}
                for inst in pm.instruments if not inst.is_drum for n in inst.notes]
    data = json.loads(path.read_text())
    return data["notes"] if isinstance(data, dict) else data


def to_arrays(notes: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    if not notes:
        return np.zeros((0, 2)), np.zeros(0)
    iv = np.array([[n["onset"], max(n["offset"], n["onset"] + 0.01)] for n in notes])
    hz = mir_eval.util.midi_to_hz(np.array([n["pitch"] for n in notes], dtype=float))
    return iv, hz


def score(ref: list[dict], est: list[dict]) -> dict:
    ri, rp = to_arrays(ref)
    ei, ep = to_arrays(est)
    out = {"n_ref": len(ref), "n_est": len(est)}
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None)
    out.update(onset_p=p, onset_r=r, onset_f1=f)
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=ONSET_TOL)
    out.update(onoff_p=p, onoff_r=r, onoff_f1=f)

    # Octave errors: unmatched reference notes that have an estimate 12/24 semitones away at the same onset.
    matched = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None)
    matched_ref = {i for i, _ in matched}
    octave = 0
    for i, n in enumerate(ref):
        if i in matched_ref:
            continue
        if any(abs(e["onset"] - n["onset"]) <= ONSET_TOL and abs(e["pitch"] - n["pitch"]) in (12, 24) for e in est):
            octave += 1
    out["octave_err_rate"] = octave / max(1, len(ref))

    # Notation-level tolerance: brass attacks read ~50 ms late, and anything under a
    # 16th note is absorbed by beat quantization.
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None)
    out.update(onset100_p=p, onset100_r=r, onset100_f1=f)

    parts = sorted({n["part"] for n in ref if "part" in n})
    for part in parts:
        sub = [n for n in ref if n.get("part") == part]
        si, sp = to_arrays(sub)
        m = mir_eval.transcription.match_notes(si, sp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None)
        out[f"recall_{part}"] = len(m) / max(1, len(sub))
        m = mir_eval.transcription.match_notes(si, sp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None)
        out[f"recall100_{part}"] = len(m) / max(1, len(sub))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("reference", type=Path)
    ap.add_argument("estimate", type=Path)
    args = ap.parse_args()
    print(json.dumps(score(load_notes(args.reference), load_notes(args.estimate)), indent=1))


if __name__ == "__main__":
    main()
