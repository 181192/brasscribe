"""Parity for source separators: stem SDR vs the reference, then note F1 of transcriptions.

For each clip the reference and converted stems are compared sample-wise (SDR in dB,
reference as signal). The stems that the song pipeline transcribes are then written as
WAV and transcribed with SwiftF0 (in-process, upstream ONNX) and Basic Pitch (the adapter
in the main checkout), and the converted stem's notes are scored against the reference
stem's notes.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np

from . import parity as P

BASIC_PITCH = P.ADAPTERS / "basic-pitch" / "run.sh"


def write_wav(path: Path, audio: np.ndarray, sr: int) -> Path:
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(audio, np.float32).T if audio.ndim == 2 and audio.shape[0] <= 2 else audio, sr,
             subtype="FLOAT")
    return path


def swift_f0_notes(path: Path) -> P.Notes:
    import math
    from swift_f0 import SwiftF0, segment_notes
    det = _swift_f0()
    notes = segment_notes(det.detect_file(str(path)), pitch_hold_ms=80.0)
    return [(n.start, n.end, float(round(69 + 12 * math.log2(n.pitch_hz / 440.0)))) for n in notes]


_DET = None


def _swift_f0():
    global _DET
    if _DET is None:
        from swift_f0 import SwiftF0
        _DET = SwiftF0()
    return _DET


def basic_pitch_notes(path: Path) -> P.Notes:
    # Keyed on the WAV's content: a stem that changed (a regressed separator) is transcribed again.
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    mid = path.with_suffix(f".{digest}.bp.mid")
    if not mid.exists():
        subprocess.run([str(BASIC_PITCH), str(path), str(mid)], check=True, capture_output=True)
    return P.midi_notes(mid)


def compare(ref: dict[str, dict[str, np.ndarray]], est: dict[str, dict[str, np.ndarray]], sr: int,
            transcribe: list[str], workdir: Path, backend: str) -> dict:
    """ref/est: clip -> stem -> (channels, samples). Returns SDR and note-F1 summaries."""
    sdr: dict[str, dict[str, float]] = {}
    f0: dict[str, dict] = {}
    bp: dict[str, dict] = {}
    for clip, stems in ref.items():
        sdr[clip] = {s: round(P.sdr(stems[s].reshape(-1), est[clip][s].reshape(-1)), 2) for s in stems}
        for s in transcribe:
            if s not in stems:
                continue
            safe = clip.replace("/", "__")
            r = write_wav(workdir / "reference" / safe / f"{s}.wav", stems[s], sr)
            e = write_wav(workdir / backend / safe / f"{s}.wav", est[clip][s], sr)
            f0[f"{clip}:{s}"] = P.note_match(swift_f0_notes(r), swift_f0_notes(e))
            bp[f"{clip}:{s}"] = P.note_match(basic_pitch_notes(r), basic_pitch_notes(e))
    all_sdr = [v for d in sdr.values() for v in d.values() if np.isfinite(v)]
    return {
        "sdr_db": sdr,
        "sdr_db_min": min(all_sdr) if all_sdr else float("inf"),
        "sdr_db_median": float(np.median(all_sdr)) if all_sdr else float("inf"),
        "swift_f0_note_f1": P.pool(f0), "basic_pitch_note_f1": P.pool(bp),
        "per_stem_f1": {k: {"swift_f0": round(f0[k]["f1"], 4), "basic_pitch": round(bp[k]["f1"], 4)} for k in f0},
    }


def passes(result: dict) -> bool:
    return (result["swift_f0_note_f1"]["f1"] >= P.THRESHOLD and result["basic_pitch_note_f1"]["f1"] >= P.THRESHOLD)
