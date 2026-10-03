"""Frame-level SwiftF0 contour of a monophonic stem, saved as .npz.

Runs inside the SwiftF0 adapter's environment (it imports only swift_f0 and numpy):

    uv run --project ml/adapters/swift-f0 python eval/brasscribe_eval/swiftf0_contour.py solo.wav solo-sw.contour.npz

The file holds t (s), pitch_hz, confidence and loudness_db per 16 ms frame.
brasscribe_music.durations reads it to find where each note really ends; the
adapter's MIDI output keeps only the segmented notes, which end early when the
contour's confidence dips on a sustained, reverberant tone.
"""

from __future__ import annotations

import os

# ONNX Runtime reports to Microsoft unless this is set before it starts.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import sys

import numpy as np
from swift_f0 import SwiftF0


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    r = SwiftF0().detect_file(src)
    np.savez_compressed(dst, t=r.timestamps, pitch_hz=r.pitch_hz, confidence=r.confidence, loudness_db=r.loudness_db)
    print(f"{len(r.timestamps)} frames -> {dst}")


if __name__ == "__main__":
    main()
