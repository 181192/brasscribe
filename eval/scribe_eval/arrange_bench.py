"""Arranger benchmark on ground-truth scores (no audio involved).

Builds a Composition from reference notes with notated positions (chorales:
S = melody, A/T = harmony, B = bass; URMP: track 1 = melody, last = bass,
others = harmony), arranges it for the minimal band (or another lineup) and reports:
  melody_kept / bass_kept: source notes present in the lead / bass part (Solo Cornet /
    E♭ Bass; same onset, same pitch class; octave displacement allowed)
  harmony_fidelity: mean Jaccard of pitch-class sets per onset, source vs band
  impossible / uncomfortable: range checks over all band notes
  crossings: slots where a lower inner part sounds above a higher one

For a four-part lineup (the quartet) also, with S A T B = lead, the two inner
parts high to low, bass:
  alto_recall_exact / tenor_recall_exact: reference A (T) notes sounding at their
    onset at the same pitch in the alto (tenor) part; *_pc: by pitch class
  parallels_per_100: parallel perfect fifths and octaves between any two voices,
    per 100 changes from one onset to the next
  spacing_faults: onsets where S-A or A-T is wider than an octave
  crossings: onsets where a voice sounds above the one over it
With --reference, the same four-part metrics on the reference voices themselves.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from brasscribe_music.arranger import _perfect_parallels, arrange
from brasscribe_music.instruments import MINIMAL_BAND, Lineup, lineup_by_name
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


def _at(notes: list[Note], t: int) -> int | None:
    return next((n.pitch for n in notes if n.start <= t < n.end), None)


def four_part(voices: list[list[Note]]) -> dict:
    """Parallels, spacing and crossings of four voices (high to low) over their onsets."""
    onsets = sorted({n.start for v in voices for n in v})
    par = spacing = crossings = 0
    prev = None
    for t in onsets:
        cur = [_at(v, t) for v in voices]
        s, a, tn, b = cur
        spacing += (s is not None and a is not None and s - a > 12) or (a is not None and tn is not None and a - tn > 12)
        crossings += any(x is not None and y is not None and y > x for x, y in zip(cur, cur[1:]))
        if prev is not None:
            par += _perfect_parallels(prev, cur)
        prev = cur
    changes = max(1, len(onsets) - 1)
    return {"parallels_per_100": 100 * par / changes, "spacing_faults": spacing, "crossings": crossings}


def recall(ref: list[Note], got: list[Note]) -> tuple[float, float]:
    """Share of reference notes sounding in `got` at their onset: same pitch, same pitch class."""
    exact = pc = 0
    for n in ref:
        p = _at(got, n.start)
        exact += p == n.pitch
        pc += p is not None and p % 12 == n.pitch % 12
    return exact / max(1, len(ref)), pc / max(1, len(ref))


def satb_names(lineup: Lineup) -> list[str]:
    inner = sorted((p for p in lineup.parts if p.name not in (lineup.lead, lineup.bass)),
                   key=lambda p: -sum(p.instrument.comfortable))
    return [lineup.lead, *(p.name for p in inner), lineup.bass]


def reference_row(comp: Composition) -> dict:
    """The four-part metrics of the reference chorale voices themselves (S A T B)."""
    by_id = {v.id: v.notes for v in comp.voices}
    return four_part([by_id[k] for k in ("S", "A", "T", "B")])


def audio_quartet_row(comp: Composition, arr, reference: Path) -> dict:
    """A quartet arranged from a transcribed recording, against the chorale's own notes (in seconds):
    melody / bass kept (pitch class at each S / B onset), alto and tenor recall by pitch class, and
    the four-part metrics of the arrangement itself."""
    from brasscribe_music.quantize import BeatMap

    lineup = arr.lineup
    names = satb_names(lineup)
    beats = BeatMap(np.array(comp.beat_times))

    def secs(tick: int) -> float:
        return float(beats.to_seconds(np.array([tick / TICKS_PER_BEAT + comp.first_downbeat]))[0])

    timed = {n: [(secs(x.start), secs(x.end), x.pitch) for x in arr.parts[n]] for n in names}
    ref = [r for r in load_notes(reference) if "part" in r]

    def share(voice: str, part: str) -> float:
        notes = [r for r in ref if r["part"] == voice]
        hit = 0
        for r in notes:
            t = r["onset"] + 0.05  # just after the attack
            p = next((p for a, b, p in timed[part] if a <= t < b), None)
            hit += p is not None and p % 12 == r["pitch"] % 12
        return hit / max(1, len(notes))

    row = {"melody_kept": share("S", names[0]), "alto_recall_pc": share("A", names[1]),
           "tenor_recall_pc": share("T", names[2]), "bass_kept": share("B", names[3])}
    row.update(four_part([arr.parts[n] for n in names]))
    imp = unc = 0
    for part in lineup.parts:
        for n in arr.parts[part.name]:
            c = part.instrument.check(n.pitch)
            imp += c == "impossible"
            unc += c == "uncomfortable"
    row["impossible"], row["uncomfortable"] = imp, unc
    return row


def evaluate(comp: Composition, lineup: Lineup = MINIMAL_BAND, difficulty: str = "faithful") -> dict:
    arr = arrange(comp, lineup, difficulty)

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
             if p.name not in (lineup.lead, lineup.bass, lineup.second_bass)]
    crossings = 0
    for t in sorted({n.start for n in band_all}):
        seq = [next((n.pitch for n in arr.parts[name] if n.start <= t < n.end), None) for name in inner]
        seq = [p for p in seq if p is not None]
        crossings += any(b > a for a, b in zip(seq, seq[1:]))
    row = {"melody_kept": kept(VoiceRole.MELODY, lineup.lead), "bass_kept": kept(VoiceRole.BASS, lineup.bass),
           "harmony_fidelity": float(np.mean(jac)) if jac else 0.0, "impossible": imp, "uncomfortable": unc,
           "band_notes": len(band_all), "crossings": crossings, "warnings": len(arr.warnings)}
    if lineup.satb:
        names = satb_names(lineup)
        fp = four_part([arr.parts[n] for n in names])
        row["crossings"] = fp["crossings"]
        row["parallels_per_100"] = fp["parallels_per_100"]
        row["spacing_faults"] = fp["spacing_faults"]
        by_id = {v.id: v.notes for v in comp.voices}
        for voice, name in (("A", names[1]), ("T", names[2])):
            if voice in by_id:
                ex, pc = recall(by_id[voice], arr.parts[name])
                key = "alto" if voice == "A" else "tenor"
                row[f"{key}_recall_exact"], row[f"{key}_recall_pc"] = ex, pc
    return row, arr


QUARTET_KEYS = ["melody_kept", "bass_kept", "harmony_fidelity", "alto_recall_exact", "alto_recall_pc",
                "tenor_recall_exact", "tenor_recall_pc", "parallels_per_100", "spacing_faults", "crossings",
                "impossible", "uncomfortable", "warnings"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("--export", help="song name to also write as MusicXML + PDF")
    ap.add_argument("--lineup", choices=["minimal", "quartet"], default="minimal")
    ap.add_argument("--difficulty", choices=["faithful", "standard", "easier"], default="faithful")
    ap.add_argument("--reference", action="store_true", help="also report the four-part metrics of the reference voices")
    args = ap.parse_args()
    lineup = lineup_by_name(args.lineup)
    rows, refs = [], []
    for song in sorted(p for p in args.eval_dir.iterdir() if (p / "reference.json").exists()):
        comp = composition_from_reference(song, song.name)
        if args.reference and {v.id for v in comp.voices} == {"S", "A", "T", "B"}:
            refs.append(reference_row(comp))
        r, arr = evaluate(comp, lineup, args.difficulty)
        rows.append(r)
        print(f"{song.name[:34]:34s} " + " ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()))
        if args.export and args.export in song.name:
            out = write_musicxml(build_band_score(arr, comp), song / "arranged.musicxml", band_sounds(arr))
            comp.to_json(song / "composition.json")
            print("wrote", out)
    keys = ["melody_kept", "bass_kept", "harmony_fidelity", "impossible", "uncomfortable", "crossings"]
    if lineup.satb:
        keys += [k for k in QUARTET_KEYS if k not in keys and all(k in r for r in rows)]
    print(json.dumps({k: round(float(np.mean([r[k] for r in rows])), 3) for k in keys}))
    if refs:
        print("reference", json.dumps({k: round(float(np.mean([r[k] for r in refs])), 3) for k in refs[0]}))


if __name__ == "__main__":
    main()
