"""Frame-level SwiftF0 contour of a monophonic stem -> .npz (t, pitch_hz, confidence, loudness_db per frame).

Same output as eval/brasscribe_eval/swiftf0_contour.py; brasscribe_music.durations
reads it to find where sustained notes really end.
"""
import sys

import numpy as np
from swift_f0 import SwiftF0
from transcribe import quiet_onnxruntime

src, dst = sys.argv[1], sys.argv[2]
quiet_onnxruntime()
r = SwiftF0().detect_file(src)
with open(dst, "wb") as f:  # a file, not a name: savez would add ".npz" to a name without it
    np.savez_compressed(f, t=r.timestamps, pitch_hz=r.pitch_hz, confidence=r.confidence, loudness_db=r.loudness_db)
print(f"{len(r.timestamps)} frames -> {dst}")
