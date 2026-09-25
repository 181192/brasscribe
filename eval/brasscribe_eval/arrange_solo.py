"""Solo recording -> Composition with one melody voice -> minimal brass-band score.

The solo line follows the adopted rule for solo lines (solo_vote_bench):
SwiftF0 supplies the notes; a note is confirmed when MuScriptor or Basic
Pitch also has it; notes without SwiftF0 are dropped. Only the Solo Cornet
part carries notes; the band parts stay empty until an accompaniment exists.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from brasscribe_music.arranger import arrange
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, fill_gaps, quantize
from brasscribe_music.score_model import Composition, KeySig, Meter, Voice, VoiceRole
from brasscribe_music.spelling import key_of

from .arrange_layers_song import pitched
from .arrange_song import to_notes
from .consensus import cluster
from .lead_sheet import line


def solo_line(sw: list[dict], mus: list[dict], bp: list[dict]) -> list[dict]:
    votes = {"sw": line(sw, 52, 88, top=True), "mus": line(mus, 52, 88, top=True), "bp": line(bp, 52, 88, top=True)}
    cand = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)),
             "confidence": {3: 0.98, 2: 0.91}.get(len(c.sources), 0.54)}
            for c in cluster(votes) if "sw" in c.sources]
    return line(cand, 52, 88, top=True)


def build(beats: Path, sw: Path, mus: Path, bp: Path, title: str) -> Composition:
    b = np.loadtxt(beats)
    pos = b[:, 1].astype(int)
    downs = np.where(pos == 1)[0]
    beats_per_bar = Counter(np.diff(downs)).most_common(1)[0][0] if len(downs) > 1 else 4
    first_down = int(np.argmax(pos == 1))
    notes = solo_line(pitched(sw), pitched(mus), pitched(bp))
    if not notes:
        raise SystemExit("no solo notes found")
    onsets = np.array([n["onset"] for n in notes])
    times = choose_level(b[:, 0], onsets)
    if len(times) != len(b):
        beats_per_bar *= 2
        first_down *= 2
    earliest = float(BeatMap(times).to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT
    melody = to_notes(fill_gaps(quantize(notes, times, monophonic=True, auto_level=False), TICKS_PER_BEAT // 2), pickup, "solo")
    comp = Composition(title, [Voice("solo", VoiceRole.MELODY, melody, "solo", "solo")],
                       [Meter(0, int(beats_per_bar))], [KeySig(0, 0)], list(map(float, times)), first_down)
    _, fifths = key_of([n.start / TICKS_PER_BEAT for n in melody], [n.dur / TICKS_PER_BEAT for n in melody], [n.pitch for n in melody])
    comp.keys = [KeySig(0, fifths)]
    return comp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats", type=Path, required=True)
    ap.add_argument("--sw", type=Path, required=True, help="SwiftF0 transcription (MIDI)")
    ap.add_argument("--mus", type=Path, required=True, help="MuScriptor transcription (MIDI)")
    ap.add_argument("--bp", type=Path, required=True, help="Basic Pitch transcription (MIDI)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="Draft")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    comp = build(args.beats, args.sw, args.mus, args.bp, args.title)
    comp.to_json(args.out / "composition.json")
    arr = arrange(comp)
    xml = write_musicxml(build_band_score(arr, comp), args.out / "brass-band.musicxml", band_sounds(arr))
    print(f"solo {len(comp.voices[0].notes)} notes, {len(arr.warnings)} warnings; {xml}")


if __name__ == "__main__":
    main()
