"""Arranger benchmark on ground-truth scores (no audio involved).

Builds a Composition from reference notes with notated positions (chorales:
S = melody, A/T = harmony, B = bass; URMP: track 1 = melody, last = bass,
others = harmony), arranges it for the minimal band and reports:
  melody_kept / bass_kept: source notes present in Solo Cornet / E♭ Bass
    (same onset, same pitch class; octave displacement allowed)
  harmony_fidelity: mean Jaccard of pitch-class sets per onset, source vs band
  impossible / uncomfortable: range checks over all band notes
  crossings: slots where a lower inner part sounds above a higher one
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from brasscribe_music.arranger import arrange
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.quantize import TICKS_PER_BEAT
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole
from brasscribe_music.spelling import key_of

from .score import load_notes


def roles_for(parts: list[str]) -> dict[str, VoiceRole]:
    if set(parts) == {"S", "A", "T", "B"}:
        return {"S": VoiceRole.MELODY, "A": VoiceRole.HARMONY, "T": VoiceRole.HARMONY, "B": VoiceRole.BASS}
    ordered = sorted(parts, key=lambda p: int(p.split("-")[0]))
    roles = {p: VoiceRole.HARMONY for p in ordered}
    roles[ordered[0]] = VoiceRole.MELODY
    roles[ordered[-1]] = VoiceRole.BASS
    return roles


def composition_from_reference(song: Path, title: str) -> Composition:
    ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
    roles = roles_for(sorted({r["part"] for r in ref}))
    voices = []
    for part, role in roles.items():
        notes = [Note(r["pitch"], int(round(r["quarter"] * TICKS_PER_BEAT)), max(1, int(round(r["dur_quarter"] * TICKS_PER_BEAT))),
                      1.0, ["reference"], r["onset"], r["offset"]) for r in ref if r["part"] == part]
        voices.append(Voice(part, role, sorted(notes, key=lambda n: n.start), part))
    ts = next((r.get("time_sig") for r in ref if r.get("time_sig")), None)
    beats = int(ts.split("/")[0]) if ts else 4
    allnotes = [n for v in voices for n in v.notes]
    _, fifths = key_of([n.start / TICKS_PER_BEAT for n in allnotes], [n.dur / TICKS_PER_BEAT for n in allnotes], [n.pitch for n in allnotes])
    return Composition(title, voices, [Meter(0, beats)], [KeySig(0, fifths)])


def evaluate(comp: Composition) -> dict:
    arr = arrange(comp)

    def kept(role: VoiceRole, part: str) -> float:
        src = [n for v in comp.voices_with(role) for n in v.notes]
        got = {(n.start, n.pitch % 12) for n in arr.parts[part]}
        return sum((n.start, n.pitch % 12) in got for n in src) / max(1, len(src))

    src_all = [n for v in comp.voices for n in v.notes]
    band_all = [n for notes in arr.parts.values() for n in notes]
    jac = []
    for t in sorted({n.start for n in src_all}):
        a = {n.pitch % 12 for n in src_all if n.start <= t < n.end}
        b = {n.pitch % 12 for n in band_all if n.start <= t < n.end}
        if a:
            jac.append(len(a & b) / len(a | b))

    imp = unc = 0
    for part in arr.lineup.parts:
        for n in arr.parts[part.name]:
            c = part.instrument.check(n.pitch)
            imp += c == "impossible"
            unc += c == "uncomfortable"

    inner = [p.name for p in sorted(arr.lineup.parts, key=lambda p: -sum(p.instrument.comfortable))
             if p.name not in ("Solo Cornet", "E♭ Bass", "B♭ Bass")]
    crossings = 0
    for t in sorted({n.start for n in band_all}):
        seq = [next((n.pitch for n in arr.parts[name] if n.start <= t < n.end), None) for name in inner]
        seq = [p for p in seq if p is not None]
        crossings += any(b > a for a, b in zip(seq, seq[1:]))
    return {"melody_kept": kept(VoiceRole.MELODY, "Solo Cornet"), "bass_kept": kept(VoiceRole.BASS, "E♭ Bass"),
            "harmony_fidelity": float(np.mean(jac)) if jac else 0.0, "impossible": imp, "uncomfortable": unc,
            "band_notes": len(band_all), "crossings": crossings, "warnings": len(arr.warnings)}, arr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("--export", help="song name to also write as MusicXML + PDF")
    args = ap.parse_args()
    rows = []
    for song in sorted(p for p in args.eval_dir.iterdir() if (p / "reference.json").exists()):
        comp = composition_from_reference(song, song.name)
        r, arr = evaluate(comp)
        rows.append(r)
        print(f"{song.name[:34]:34s} " + " ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()))
        if args.export and args.export in song.name:
            out = write_musicxml(build_band_score(arr, comp), song / "arranged.musicxml", band_sounds(arr))
            comp.to_json(song / "composition.json")
            print("wrote", out)
    keys = ["melody_kept", "bass_kept", "harmony_fidelity", "impossible", "uncomfortable", "crossings"]
    print(json.dumps({k: round(float(np.mean([r[k] for r in rows])), 3) for k in keys}))


if __name__ == "__main__":
    main()
