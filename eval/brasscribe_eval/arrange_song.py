"""End-to-end: transcribed song -> Composition -> minimal brass-band score.

Melody: top line over MuScriptor-supported notes (Basic Pitch as confirmation).
Bass: bottom line of the bass-stem transcription.
Harmony: accompaniment notes (minus the melody) reduced to a per-beat
harmonic rhythm. Beats come from Beat This!; tick 0 is the first downbeat.
"""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from brasscribe_music.arranger import arrange
from brasscribe_music.harmony import harmony_slots, slots_to_notes
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, fill_gaps, quantize
from brasscribe_music.spelling import key_of
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

from .consensus import consensus
from .lead_sheet import line
from .score import load_notes


def to_notes(qnotes, pickup: int, source: str) -> list[Note]:
    return [Note(q.pitch, q.start - pickup, q.end - q.start, q.confidence, [source], q.onset_s, q.offset_s) for q in qnotes]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats", type=Path, required=True)
    ap.add_argument("--melody", type=Path, required=True)
    ap.add_argument("--melody-support", type=Path)
    ap.add_argument("--bass", type=Path, required=True)
    ap.add_argument("--harmony", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True, help="output directory")
    ap.add_argument("--title", default="Draft")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    b = np.loadtxt(args.beats)
    pos = b[:, 1].astype(int)
    beats_per_bar = Counter(np.diff(np.where(pos == 1)[0])).most_common(1)[0][0]
    first_down = int(np.argmax(pos == 1))
    # Fix the metrical level once from all transcribed onsets, then quantize every stream on that grid.
    all_onsets = np.array([n["onset"] for f in [args.melody, args.bass, *args.harmony] for n in load_notes(f)])
    times = choose_level(b[:, 0], all_onsets)
    if len(times) != len(b):
        beats_per_bar *= 2
        first_down *= 2
    # Tick 0 is the downbeat at or before the earliest note, so nothing precedes bar 1.
    earliest = float(BeatMap(times).to_beats(np.array([all_onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT

    sources = {"mus": load_notes(args.melody)}
    if args.melody_support:
        sources["bp"] = load_notes(args.melody_support)
    cand, _ = consensus(sources, {"mus": 0.6, "bp": 0.4}, 0.5)
    mel_raw = line(cand, 52, 88, top=True)
    melody = to_notes(fill_gaps(quantize(mel_raw, times, monophonic=True, auto_level=False), TICKS_PER_BEAT // 2), pickup, "melody")
    bass = to_notes(fill_gaps(quantize(line(load_notes(args.bass), 28, 55, top=False), times, monophonic=True, auto_level=False),
                              TICKS_PER_BEAT // 2), pickup, "bass")

    mel_keys = {(round(n["onset"], 2), n["pitch"]) for n in mel_raw}
    acc = [n for f in args.harmony for n in load_notes(f)
           if 40 <= n["pitch"] <= 84 and (round(n["onset"], 2), n["pitch"]) not in mel_keys]
    acc_q = to_notes(quantize(acc, times, auto_level=False), pickup, "accompaniment")
    end = max(n.end for n in melody + bass + acc_q)
    harm = slots_to_notes(harmony_slots(acc_q, end), confidence=0.8)

    comp = Composition(args.title, [Voice("melody", VoiceRole.MELODY, melody), Voice("bass", VoiceRole.BASS, bass),
                                    Voice("harmony", VoiceRole.HARMONY, harm)],
                       [Meter(0, int(beats_per_bar))], [KeySig(0, 0)], list(map(float, times)), first_down)
    tonal = melody + bass + harm
    _, fifths = key_of([n.start / TICKS_PER_BEAT for n in tonal], [n.dur / TICKS_PER_BEAT for n in tonal], [n.pitch for n in tonal])
    comp.keys = [KeySig(0, fifths)]
    comp.to_json(args.out / "composition.json")
    arr = arrange(comp)
    xml = write_musicxml(build_band_score(arr, comp), args.out / "brass-band.musicxml", band_sounds(arr))
    pdf = xml.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    subprocess.run(["mscore", "-o", str(pdf), str(xml)], capture_output=True)
    print(f"{len(melody)} melody / {len(bass)} bass / {len(harm)} harmony notes, {len(arr.warnings)} warnings")
    print(xml, pdf if pdf.exists() else "(no PDF)")


if __name__ == "__main__":
    main()
