"""Monophonic transcription: SwiftF0 pitch contour -> DP note segmentation -> MIDI.

A recording in which it hears no note (silence, noise, chords it cannot follow) gets a MIDI file with no
notes: the adapter's contract is an output file, and "no notes" is an answer, not a failure.
"""
import sys


def write_notes(notes, dst: str) -> None:
    """`notes` as MIDI at `dst`; a file without notes when there are none (swift_f0 refuses to export those)."""
    if notes:
        from swift_f0 import export_to_midi

        export_to_midi(notes, dst)
    else:
        import pretty_midi

        pretty_midi.PrettyMIDI().write(dst)


def quiet_onnxruntime() -> None:
    """ORT_DISABLE_TELEMETRY (run_adapter.py) keeps ONNX Runtime from reporting to Microsoft, except on
    Windows, where it reports through ETW and only this call turns its events off."""
    import onnxruntime

    getattr(onnxruntime, "disable_telemetry_events", lambda: None)()


def main(src: str, dst: str) -> None:
    from swift_f0 import SwiftF0, segment_notes

    quiet_onnxruntime()
    result = SwiftF0().detect_file(src)
    notes = segment_notes(result, pitch_hold_ms=80.0)
    write_notes(notes, dst)
    print(f"{len(notes)} notes")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
