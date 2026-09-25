"""Solo-with-band arrangement from textural layers (see brasscribe_music.arranger.arrange_layers).

Layers (from layers.py): solo (Mega-53 trumpet), bass, drums, and the orchestra
residual (mix minus solo, bass and drums). The orchestra is split by what the
notes do rather than by timbre, because the separators cannot tell this
recording's strings, keys and orchestral brass apart reliably:
  short notes attacked together with two or more others -> brass choir hits
  everything else -> strings (pads + countermelody)
"""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pretty_midi
from brasscribe_music.arranger import arrange_layers
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, fill_gaps, quantize
from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole
from brasscribe_music.spelling import key_of

from .arrange_song import to_notes
from .consensus import consensus
from .lead_sheet import line


def pitched(path: Path) -> list[dict]:
    pm = pretty_midi.PrettyMIDI(str(path))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if not i.is_drum for n in i.notes]


def drums_of(path: Path) -> list[dict]:
    pm = pretty_midi.PrettyMIDI(str(path))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if i.is_drum for n in i.notes]


def split_orchestra(notes: list[Note]) -> tuple[list[Note], list[Note]]:
    """(hits, lines): short notes sharing an attack with >= 2 others are chordal hits."""
    by_start = Counter(n.start for n in notes)
    hits = [n for n in notes if by_start[n.start] >= 3 and n.dur <= TICKS_PER_BEAT]
    hit_ids = {id(n) for n in hits}
    return hits, [n for n in notes if id(n) not in hit_ids]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=Path, required=True)
    ap.add_argument("--beats", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="Draft")
    args = ap.parse_args()
    L = args.layers
    args.out.mkdir(parents=True, exist_ok=True)

    solo_mus, solo_bp = pitched(L / "solo-mus.mid"), pitched(L / "solo-bp.mid")
    bass_raw = pitched(L / "bass-mus.mid")
    orch_raw = pitched(L / "orchestra-mus.mid")
    drum_raw = drums_of(L / "drums-mus.mid")

    b = np.loadtxt(args.beats)
    pos = b[:, 1].astype(int)
    beats_per_bar = Counter(np.diff(np.where(pos == 1)[0])).most_common(1)[0][0]
    first_down = int(np.argmax(pos == 1))
    onsets = np.array([n["onset"] for n in solo_mus + solo_bp + bass_raw + orch_raw])
    times = choose_level(b[:, 0], onsets)
    if len(times) != len(b):
        beats_per_bar *= 2
        first_down *= 2
    earliest = float(BeatMap(times).to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT
    half = TICKS_PER_BEAT // 2

    # Solo: MuScriptor-supported notes where MuScriptor hears the soloist; where it is
    # silent (the quiet intro), Basic Pitch is the only evidence and its notes stay,
    # flagged as unconfirmed (confidence 0.4).
    cand, _ = consensus({"mus": solo_mus, "bp": solo_bp}, {"mus": 0.6, "bp": 0.4}, 0.0)
    mus_on = np.array(sorted(n["onset"] for n in solo_mus))

    def mus_nearby(t: float, window: float = 1.5) -> bool:
        i = np.searchsorted(mus_on, t)
        return any(abs(mus_on[j] - t) <= window for j in (i - 1, i) if 0 <= j < len(mus_on))

    cand = [n for n in cand if n["confidence"] >= 0.5 or not mus_nearby(n["onset"])]
    solo_line = line(cand, 52, 88, top=True)
    solo = to_notes(fill_gaps(quantize(solo_line, times, monophonic=True, auto_level=False), half), pickup, "solo")
    bass = to_notes(fill_gaps(quantize(line(bass_raw, 24, 55, top=False), times, monophonic=True, auto_level=False), half),
                    pickup, "bass")

    solo_keys = {(round(n["onset"], 1), n["pitch"]) for n in solo_line}
    orch = [n for n in orch_raw if 36 <= n["pitch"] <= 88 and (round(n["onset"], 1), n["pitch"]) not in solo_keys]
    orch_q = [n for n in to_notes(quantize(orch, times, auto_level=False), pickup, "orchestra") if n.start >= 0]
    hits, lines = split_orchestra(orch_q)

    dq = quantize(drum_raw, times, auto_level=False)
    starts = sorted({q.start for q in dq})
    nxt = {s: n for s, n in zip(starts, starts[1:])}
    drums = [Note(q.pitch, q.start - pickup, min(nxt.get(q.start, q.start + half) - q.start, TICKS_PER_BEAT), 1.0, ["drums"])
             for q in dq if q.start - pickup >= 0]

    comp = Composition(args.title, [
        Voice("solo", VoiceRole.MELODY, solo, "trumpet/cornet", "solo"),
        Voice("bass", VoiceRole.BASS, bass, "electric bass", "bass"),
        Voice("strings", VoiceRole.HARMONY, lines, "orchestra", "strings"),
        Voice("brass", VoiceRole.HARMONY, hits, "orchestra hits", "brass"),
        Voice("drums", VoiceRole.RHYTHM, drums, "drum kit", "drums"),
    ], [Meter(0, int(beats_per_bar))], [KeySig(0, 0)], list(map(float, times)), first_down)
    tonal = solo + bass + lines
    _, fifths = key_of([n.start / TICKS_PER_BEAT for n in tonal], [n.dur / TICKS_PER_BEAT for n in tonal], [n.pitch for n in tonal])
    comp.keys = [KeySig(0, fifths)]
    comp.to_json(args.out / "composition.json")

    arr = arrange_layers(comp)
    xml = write_musicxml(build_band_score(arr, comp), args.out / "brass-band.musicxml", band_sounds(arr))
    for ext in ("pdf", "mp3"):
        f = xml.with_suffix(f".{ext}")
        f.unlink(missing_ok=True)
        subprocess.run(["mscore", "-o", str(f), str(xml)], capture_output=True)
    counts = {k: len(v) for k, v in arr.parts.items()}
    print(f"solo {len(solo)}, bass {len(bass)}, orchestra lines {len(lines)} / hits {len(hits)}, drums {len(drums)}")
    print("band notes per part:", counts)
    print(f"key fifths {fifths}; warnings {len(arr.warnings)}")
    print(xml, "pdf" if xml.with_suffix(".pdf").exists() else "(no pdf)", "mp3" if xml.with_suffix(".mp3").exists() else "(no mp3)")


if __name__ == "__main__":
    main()
