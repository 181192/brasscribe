"""Notated-duration accuracy: performed notes -> written lengths, against the score.

Reference notes (performed onset/offset from the annotations, notated
`quarter`/`dur_quarter` from the score alignment) are quantized on the
reference beat grid as one ensemble, then each part gets its written
durations from one of the rules below. A written length is correct when it is
within 1 tick (1/24 beat) of the notated one; URMP score MIDI stores a quarter
as 23/24.

Rules:
  performed   performed length, snapped
  fill8       hold until the next onset when the gap is <= an 8th (the previous rule)
  audio       brasscribe_music.durations.written_durations: legato vs detached from
              the performed length relative to the time to the next onset, plus
              staccato when the performed length is under half the written one

--contours DIR replaces each reference offset by the end found in a SwiftF0
contour of that part's own track (DIR/<song>/<part>.npz, made by
track_contours.py), i.e. offsets measured from audio instead of annotated.
Onsets and pitches stay the reference ones, so only the offset source changes.

    uv run python -W ignore -m brasscribe_eval.duration_bench ../data/eval/urmp-brass
    uv run python -W ignore -m brasscribe_eval.duration_bench ../data/eval/urmp-brass --contours ../data/runs/contours/urmp-brass
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from brasscribe_music.durations import SEPARATED_STEM, Contour, contour_offsets, written_durations
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, QNote, fill_gaps, quantize

from .quant_bench import reference_beats
from .score import load_notes

RULES = ("performed", "fill8", "audio")


def _written(rule: str, part: list[QNote], bm: BeatMap) -> list[tuple[int, bool]]:
    """(written length in ticks, staccato) per note of one part, in input order."""
    if rule == "performed":
        return [(q.end - q.start, False) for q in part]
    if rule == "fill8":
        orig = [(q.start, q.end) for q in part]
        fill_gaps(part, TICKS_PER_BEAT // 2)
        out = [(q.end - q.start, False) for q in part]
        for q, (s, e) in zip(part, orig):
            q.start, q.end = s, e
        return out
    res = written_durations(part, bm)
    return [(w.dur, w.staccato) for w in res]


def evaluate(song: Path, contours: Path | None = None, stem_settings: bool = False) -> dict:
    ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
    off_err = []
    if contours is not None:
        cdir = contours / song.name
        by_part = defaultdict(list)
        for r in ref:
            by_part[r["part"]].append(r)
        for part, notes in by_part.items():
            f = cdir / f"{part}.npz"
            if not f.exists():
                raise FileNotFoundError(f"missing contour {f}")
            notes.sort(key=lambda r: r["onset"])
            offs = contour_offsets(Contour.load(f), [(r["onset"], r["pitch"]) for r in notes],
                                   **(SEPARATED_STEM if stem_settings else {}))
            for r, o in zip(notes, offs):
                off_err.append(o - r["offset"])
                r["offset"] = o
    beats = reference_beats(song)
    bm = BeatMap(beats)
    q = quantize(ref, beats, auto_level=False)
    # (onset, pitch, offset): parts in unison on one onset keep their own lengths
    by_key = {(round(x.onset_s, 6), x.pitch, round(x.offset_s, 6)): x for x in q}
    parts: dict[str, list[tuple[dict, QNote]]] = defaultdict(list)
    for r in ref:
        parts[r["part"]].append((r, by_key[(round(r["onset"], 6), r["pitch"], round(r["offset"], 6))]))
    counts = {k: 0 for k in RULES}
    stacc = stacc_short = 0
    n = 0
    for items in parts.values():
        items.sort(key=lambda it: it[1].start)
        qs = [QNote(x.pitch, x.start, x.end, x.onset_s, x.offset_s) for _, x in items]
        want = [int(round(r["dur_quarter"] * TICKS_PER_BEAT)) for r, _ in items]
        for rule in RULES:
            got = _written(rule, [QNote(x.pitch, x.start, x.end, x.onset_s, x.offset_s) for x in qs], bm)
            counts[rule] += sum(abs(g - w) <= 1 for (g, _), w in zip(got, want))
            if rule == "audio":
                for (g, st), w in zip(got, want):
                    if st:
                        stacc += 1
                        stacc_short += w < g - 1  # the score wrote it shorter than we did (e.g. 8th + rest)
        n += len(items)
    out = {"n": n}
    out.update({k: counts[k] / max(1, n) for k in RULES})
    out["staccato"] = stacc
    out["staccato_where_score_shorter"] = stacc_short
    if off_err:
        out["offset_err_median_s"] = float(np.median(off_err))
        out["offset_within_100ms"] = float(np.mean(np.abs(off_err) <= 0.1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("--contours", type=Path, help="per-track SwiftF0 contours; offsets come from them")
    ap.add_argument("--stem-settings", action="store_true", help="follow contours with the separated-stem settings")
    args = ap.parse_args()
    rows = []
    for song in sorted(p for p in args.eval_dir.iterdir() if (p / "reference.json").exists()):
        r = evaluate(song, args.contours, args.stem_settings)
        rows.append(r)
        print(f"{song.name:42s} " + " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()))
    tot = sum(r["n"] for r in rows)
    summary = {k: round(sum(r[k] * r["n"] for r in rows) / tot, 3) for k in RULES}
    summary["mean_over_pieces"] = {k: round(float(np.mean([r[k] for r in rows])), 3) for k in RULES}
    summary["staccato"] = sum(r["staccato"] for r in rows)
    if args.contours:
        summary["offset_within_100ms"] = round(sum(r["offset_within_100ms"] * r["n"] for r in rows) / tot, 3)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
