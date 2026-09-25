"""Monophonic transcription: SwiftF0 pitch contour -> DP note segmentation -> MIDI."""
import sys

from swift_f0 import SwiftF0, export_to_midi, segment_notes

src, dst = sys.argv[1], sys.argv[2]
result = SwiftF0().detect_file(src)
notes = segment_notes(result, pitch_hold_ms=80.0)
export_to_midi(notes, dst)
print(f"{len(notes)} notes")
