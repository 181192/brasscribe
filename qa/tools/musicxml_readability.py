# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Readability heuristics for brass-band MusicXML (score-partwise).

Stdlib only, so it runs in CI with `uv run qa/tools/musicxml_readability.py`.

Reports per part and for the whole score:
  - share of notes shorter than a 16th, and the share that are exactly 16ths
  - tuplet density, double-dotted values, tie stubs (a tie ending on a 16th or shorter)
  - rests per non-empty bar and rests shorter than an eighth
  - ledger lines (max, and share of notes with 3 or more) from written pitch and clef
  - written range against heuristic brass-band instrument ranges
  - awkward spellings (E#, B#, Cb, Fb, double accidentals), printed-accidental density,
    bars mixing sharps and flats, leaps over an octave
  - empty-bar ratio, and runs of empty bars that should be multi-bar rests in parts
  - colour-only uncertainty (coloured notes without a distinct notehead)
  - divisi (chords in a monophonic brass part)

`--bars` lists every flagged bar with reasons. `--range A-B` restricts to bars A..B.
`--check` exits 1 when a threshold in THRESHOLDS is exceeded (CI gate).
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

STEP_INDEX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
STEP_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Written ranges as MIDI numbers: (extreme_low, comfort_low, comfort_high, extreme_high).
# Heuristic defaults for a British-style brass band (treble-clef transposing parts,
# bass trombone in concert bass clef). Not authoritative; see qa/reviews for the open question.
# Matched in order against the lower-cased part name.
RANGES: list[tuple[str, tuple[int, int, int, int]]] = [
    ("soprano", (54, 60, 81, 86)),       # F#3  C4  A5  D6
    ("solo cornet", (54, 57, 84, 86)),   # F#3  A3  C6  D6
    ("cornet", (54, 57, 81, 84)),        # F#3  A3  A5  C6
    ("flugel", (54, 57, 79, 84)),        # F#3  A3  G5  C6
    ("horn", (54, 57, 79, 84)),          # tenor horn in Eb
    ("baritone", (54, 57, 79, 84)),
    ("bass trombone", (28, 36, 60, 65)), # concert, bass clef: E1 C2 C4 F4
    ("trombone", (54, 57, 81, 86)),      # Bb treble
    ("euphonium", (48, 54, 81, 86)),     # C3 F#3 A5 D6
    ("e♭ bass", (48, 54, 74, 79)),
    ("eb bass", (48, 54, 74, 79)),
    ("b♭ bass", (48, 54, 74, 79)),
    ("bb bass", (48, 54, 74, 79)),
]

# CI thresholds. Per-part checks skip tacet parts and percussion.
THRESHOLDS = {
    "short_lt16_pct": 2.0,        # notes shorter than a 16th
    "sixteenth_pct": 35.0,        # notes that are 16ths
    "tuplet_pct": 15.0,
    "tie_stub_pct": 3.0,          # ties that end on a 16th or shorter
    "double_dotted": 0,
    "rests_per_bar": 2.5,         # mean rests per non-empty bar
    "short_rest_pct": 30.0,       # rests shorter than an eighth, as % of rests
    "max_ledger": 4,
    "ledger3_pct": 5.0,
    "out_of_extreme": 0,
    "awkward_spelling": 0,
    "accidental_pct": 25.0,       # notes with a printed accidental
    "colour_only_uncertain": 0,
    "divisi_notes": 0,
}

UNCERTAIN_NOTEHEADS = {"diamond", "x", "circle-x", "triangle", "slash", "square", "cross"}

SIXTEENTH = Fraction(1, 4)  # in quarter notes
EIGHTH = Fraction(1, 2)


@dataclass
class Note:
    bar: str
    onset: Fraction          # quarters from bar start
    dur: Fraction            # quarters
    midi: int | None         # written pitch
    step: str | None
    alter: int
    octave: int | None
    dots: int
    tuplet: bool
    tie_start: bool
    tie_stop: bool
    colour: str | None
    notehead: str | None
    accidental: str | None = None  # printed accidental
    ledgers: int = 0


@dataclass
class Part:
    pid: str
    name: str
    abbreviation: str
    percussion: bool = False
    bars: list[str] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    rests: list[Note] = field(default_factory=list)
    divisi: list[str] = field(default_factory=list)  # bar numbers of chord notes


def _t(el: ET.Element | None, path: str, default: str | None = None) -> str | None:
    if el is None:
        return default
    x = el.find(path)
    return x.text if x is not None and x.text is not None else default


def ledger_lines(step: str, octave: int, clef: tuple[str, int]) -> int:
    """Ledger lines needed for a written pitch on a five-line staff."""
    idx = octave * 7 + STEP_INDEX[step]
    sign, line = clef
    if sign == "G":
        bottom = 4 * 7 + STEP_INDEX["E"] + (line - 2) * 2
    elif sign == "F":
        bottom = 2 * 7 + STEP_INDEX["G"] + (line - 4) * 2
    elif sign == "C":
        bottom = 3 * 7 + STEP_INDEX["F"] + (line - 3) * 2
    else:
        return 0
    top = bottom + 8
    if idx > top:
        return (idx - top) // 2
    if idx < bottom:
        return (bottom - idx) // 2
    return 0


def parse(path: Path) -> tuple[list[Part], dict]:
    root = ET.parse(path).getroot()
    if root.tag != "score-partwise":
        raise SystemExit(f"{path}: only score-partwise is supported (got {root.tag})")
    names: dict[str, tuple[str, str]] = {}
    for sp in root.iter("score-part"):
        names[sp.get("id", "")] = (_t(sp, "part-name", "") or "", _t(sp, "part-abbreviation", "") or "")
    score: dict = {"dynamics": 0, "words": [], "rehearsal": 0, "tempos": 0,
                   "time_changes": 0, "key_changes": 0}
    parts: list[Part] = []
    for p_el in root.findall("part"):
        pid = p_el.get("id", "")
        name, abbr = names.get(pid, (pid, ""))
        part = Part(pid, name, abbr)
        divisions = 1
        clef = ("G", 2)
        first_part = not parts
        for m in p_el.findall("measure"):
            bar = m.get("number", "?")
            part.bars.append(bar)
            pos = Fraction(0)
            last_onset = Fraction(0)
            for el in m:
                tag = el.tag
                if tag == "attributes":
                    d = _t(el, "divisions")
                    if d:
                        divisions = int(d)
                    c = el.find("clef")
                    if c is not None:
                        sign = _t(c, "sign", "G") or "G"
                        clef = (sign, int(_t(c, "line", "2") or 2))
                        if sign == "percussion":
                            part.percussion = True
                    if first_part and part.bars != [part.bars[0]]:
                        if el.find("time") is not None:
                            score["time_changes"] += 1
                        if el.find("key") is not None:
                            score["key_changes"] += 1
                elif tag == "direction" and first_part:
                    for dt in el.iter("direction-type"):
                        if dt.find("dynamics") is not None:
                            score["dynamics"] += 1
                        if dt.find("rehearsal") is not None:
                            score["rehearsal"] += 1
                        if dt.find("metronome") is not None:
                            score["tempos"] += 1
                        for w in dt.findall("words"):
                            if w.text:
                                score["words"].append((bar, w.text.strip()))
                elif tag == "direction":
                    if any(dt.find("dynamics") is not None for dt in el.iter("direction-type")):
                        score["dynamics"] += 1
                elif tag == "backup":
                    pos -= Fraction(int(_t(el, "duration", "0") or 0), divisions)
                elif tag == "forward":
                    pos += Fraction(int(_t(el, "duration", "0") or 0), divisions)
                elif tag == "note":
                    if el.find("grace") is not None:
                        continue
                    dur = Fraction(int(_t(el, "duration", "0") or 0), divisions)
                    is_chord = el.find("chord") is not None
                    onset = last_onset if is_chord else pos
                    ties = [t.get("type") for t in el.findall("tie")]
                    n = Note(
                        bar=bar, onset=onset, dur=dur, midi=None, step=None, alter=0,
                        octave=None, dots=len(el.findall("dot")),
                        tuplet=el.find("time-modification") is not None,
                        tie_start="start" in ties, tie_stop="stop" in ties,
                        colour=el.get("color"), notehead=_t(el, "notehead"),
                        accidental=_t(el, "accidental"),
                    )
                    if el.find("rest") is not None:
                        part.rests.append(n)
                    elif el.find("pitch") is not None:
                        pe = el.find("pitch")
                        n.step = _t(pe, "step")
                        n.octave = int(_t(pe, "octave", "4") or 4)
                        n.alter = int(float(_t(pe, "alter", "0") or 0))
                        n.midi = 12 * (n.octave + 1) + STEP_SEMITONE[n.step] + n.alter
                        n.ledgers = ledger_lines(n.step, n.octave, clef)
                        if is_chord and not part.percussion:
                            part.divisi.append(bar)
                        else:
                            part.notes.append(n)
                    elif el.find("unpitched") is not None:
                        part.percussion = True
                        if not is_chord:
                            part.notes.append(n)
                    if not is_chord:
                        last_onset = pos
                        pos += dur
        parts.append(part)
    return parts, score


def in_range(bar: str, rng: tuple[int, int] | None) -> bool:
    if rng is None:
        return True
    try:
        b = int(bar)
    except ValueError:
        return True
    return rng[0] <= b <= rng[1]


def range_for(name: str) -> tuple[int, int, int, int] | None:
    low = name.lower()
    for key, r in RANGES:
        if key in low:
            return r
    return None


def midi_name(m: int) -> str:
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return f"{names[m % 12]}{m // 12 - 1}"


def pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


def awkward(n: Note) -> bool:
    return abs(n.alter) >= 2 or (n.step, n.alter) in {("E", 1), ("B", 1), ("C", -1), ("F", -1)}


def analyse_part(part: Part, rng: tuple[int, int] | None) -> tuple[dict, dict[str, list[str]]]:
    bars = [b for b in part.bars if in_range(b, rng)]
    notes = [n for n in part.notes if in_range(n.bar, rng)]
    rests = [r for r in part.rests if in_range(r.bar, rng)]
    divisi = [b for b in part.divisi if in_range(b, rng)]
    flags: dict[str, list[str]] = {}

    def flag(bar: str, reason: str) -> None:
        lst = flags.setdefault(bar, [])
        if reason not in lst:
            lst.append(reason)

    bars_with_notes = {n.bar for n in notes}
    empty = [b for b in bars if b not in bars_with_notes]
    # runs of 4+ empty bars
    runs, cur = [], []
    for b in bars:
        if b in bars_with_notes:
            if len(cur) >= 4:
                runs.append((cur[0], cur[-1]))
            cur = []
        else:
            cur.append(b)
    if len(cur) >= 4:
        runs.append((cur[0], cur[-1]))

    m: dict = {
        "part": part.name,
        "abbreviation": part.abbreviation,
        "bars": len(bars),
        "notes": len(notes),
        "empty_bars": len(empty),
        "empty_bar_pct": pct(len(empty), len(bars)),
        "empty_runs_ge4": len(runs),
        "tacet": not notes,
        "percussion": part.percussion,
    }
    if not notes:
        return m, flags

    short = [n for n in notes if n.dur < SIXTEENTH and not n.tuplet]
    six = [n for n in notes if n.dur == SIXTEENTH]
    tup = [n for n in notes if n.tuplet]
    dd = [x for x in notes + rests if x.dots >= 2]
    stubs = [n for n in notes if n.tie_stop and n.dur <= SIXTEENTH]
    ties = [n for n in notes if n.tie_start]
    short_rests = [r for r in rests if r.dur < EIGHTH]
    uncertain = [n for n in notes if n.colour and n.colour.upper() not in {"#000000", "#000"}]
    colour_only = [n for n in uncertain if (n.notehead or "normal") not in UNCERTAIN_NOTEHEADS]
    offgrid = [n for n in notes if not n.tuplet and (n.onset / EIGHTH).denominator != 1]
    rests_by_bar: dict[str, int] = {}
    for r in rests:
        if r.bar in bars_with_notes:
            rests_by_bar[r.bar] = rests_by_bar.get(r.bar, 0) + 1
    notes_by_bar: dict[str, int] = {}
    for n in notes:
        notes_by_bar[n.bar] = notes_by_bar.get(n.bar, 0) + 1

    for n in short:
        flag(n.bar, "shorter than 16th")
    for x in dd:
        flag(x.bar, "double-dotted value")
    for n in stubs:
        flag(n.bar, "tie into 16th")
    for b, c in rests_by_bar.items():
        if c >= 4:
            flag(b, f"{c} rests")
    for n in uncertain:
        flag(n.bar, "uncertain (colour)")
    for b in divisi:
        flag(b, "divisi chord")

    m.update({
        "short_lt16_pct": pct(len(short), len(notes)),
        "sixteenth_pct": pct(len(six), len(notes)),
        "tuplet_pct": pct(len(tup), len(notes)),
        "double_dotted": len(dd),
        "tie_pct": pct(len(ties), len(notes)),
        "tie_stub_pct": pct(len(stubs), len(notes)),
        "offbeat_16th_onset_pct": pct(len(offgrid), len(notes)),
        "rests_per_bar": round(sum(rests_by_bar.values()) / len(bars_with_notes), 2) if bars_with_notes else 0.0,
        "short_rest_pct": pct(len(short_rests), len(rests)),
        "max_notes_per_bar": max(notes_by_bar.values()),
        "uncertain_pct": pct(len(uncertain), len(notes)),
        "colour_only_uncertain": len(colour_only),
        "divisi_notes": len(divisi),
    })

    if part.percussion:
        return m, flags

    pitched = [n for n in notes if n.midi is not None]
    led = [n.ledgers for n in pitched]
    aw = [n for n in pitched if awkward(n)]
    for n in pitched:
        if n.ledgers >= 3:
            flag(n.bar, f"{n.ledgers} ledger lines ({midi_name(n.midi)})")
        if awkward(n):
            flag(n.bar, f"awkward spelling {n.step}{'#' * max(n.alter, 0)}{'b' * max(-n.alter, 0)}")
    leaps = 0
    for a, b in zip(pitched, pitched[1:]):
        if abs(a.midi - b.midi) > 12:
            leaps += 1
            flag(b.bar, f"leap {abs(a.midi - b.midi)} semitones")
    acc = [n for n in pitched if n.accidental]
    acc_by_bar: dict[str, set[str]] = {}
    acc_count: dict[str, int] = {}
    for n in acc:
        acc_by_bar.setdefault(n.bar, set()).add(n.accidental)
        acc_count[n.bar] = acc_count.get(n.bar, 0) + 1
    mixed = [b for b, kinds in acc_by_bar.items() if {"sharp", "flat"} <= kinds]
    for b in mixed:
        flag(b, "sharps and flats mixed")
    for b, c in acc_count.items():
        if c >= 6:
            flag(b, f"{c} accidentals")
    lo, hi = min(n.midi for n in pitched), max(n.midi for n in pitched)
    m.update({
        "written_low": midi_name(lo),
        "written_high": midi_name(hi),
        "max_ledger": max(led),
        "ledger3_pct": pct(sum(1 for x in led if x >= 3), len(led)),
        "awkward_spelling": len(aw),
        "accidental_pct": pct(len(acc), len(pitched)),
        "bars_mixed_sharp_flat": len(mixed),
        "leaps_gt_octave": leaps,
    })
    r = range_for(part.name)
    if r:
        ext_lo, com_lo, com_hi, ext_hi = r
        out_c = [n for n in pitched if n.midi < com_lo or n.midi > com_hi]
        out_e = [n for n in pitched if n.midi < ext_lo or n.midi > ext_hi]
        for n in out_e:
            flag(n.bar, f"outside range ({midi_name(n.midi)})")
        m.update({
            "range_ref": f"{midi_name(ext_lo)}..{midi_name(ext_hi)} (comfort {midi_name(com_lo)}..{midi_name(com_hi)})",
            "out_of_comfort_pct": pct(len(out_c), len(pitched)),
            "out_of_extreme": len(out_e),
        })
    return m, flags


def violations(metrics: list[dict]) -> list[str]:
    out = []
    for m in metrics:
        if m["tacet"]:
            continue
        for key, limit in THRESHOLDS.items():
            if key in m and m[key] > limit:
                out.append(f"{m['part']}: {key}={m[key]} > {limit}")
    return out


def aggregate(metrics: list[dict], parts: list[Part], rng) -> dict:
    playing = [p for p, m in zip(parts, metrics) if not m["tacet"] and not p.percussion]
    notes = [n for p in playing for n in p.notes if in_range(n.bar, rng)]
    bars = sum(len([b for b in p.bars if in_range(b, rng)]) for p in playing)
    empty = sum(m["empty_bars"] for p, m in zip(parts, metrics) if p in playing)
    abbr: dict[str, list[str]] = {}
    for p in parts:
        abbr.setdefault(p.abbreviation, []).append(p.name)
    return {
        "parts": len(parts),
        "tacet_parts": [m["part"] for m in metrics if m["tacet"]],
        "pitched_notes": len(notes),
        "short_lt16_pct": pct(sum(1 for n in notes if n.dur < SIXTEENTH and not n.tuplet), len(notes)),
        "sixteenth_pct": pct(sum(1 for n in notes if n.dur == SIXTEENTH), len(notes)),
        "tuplet_pct": pct(sum(1 for n in notes if n.tuplet), len(notes)),
        "tie_stub_pct": pct(sum(1 for n in notes if n.tie_stop and n.dur <= SIXTEENTH), len(notes)),
        "empty_bar_pct_playing_parts": pct(empty, bars),
        "uncertain_pct": pct(sum(1 for n in notes if n.colour), len(notes)),
        "duplicate_abbreviations": {k: v for k, v in abbr.items() if len(v) > 1},
    }


def md_report(path: Path, score: dict, agg: dict, metrics: list[dict], rng) -> str:
    cols = ["part", "notes", "empty_bar_pct", "short_lt16_pct", "sixteenth_pct", "tuplet_pct",
            "double_dotted", "tie_stub_pct", "rests_per_bar", "short_rest_pct", "max_ledger",
            "ledger3_pct", "written_low", "written_high", "out_of_comfort_pct", "out_of_extreme",
            "awkward_spelling", "accidental_pct", "bars_mixed_sharp_flat", "leaps_gt_octave", "uncertain_pct", "colour_only_uncertain"]
    lines = [f"# Readability: {path.name}" + (f" (bars {rng[0]}-{rng[1]})" if rng else ""), ""]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for m in metrics:
        lines.append("| " + " | ".join(str(m.get(c, "tacet" if m["tacet"] else "")) for c in cols) + " |")
    lines += ["", "Score:", ""]
    for k, v in agg.items():
        lines.append(f"- {k}: {v}")
    lines.append(f"- dynamics markings: {score['dynamics']}, rehearsal marks: {score['rehearsal']}, "
                 f"tempo marks: {score['tempos']}, text directions: {len(score['words'])}, "
                 f"time changes: {score['time_changes']}, key changes: {score['key_changes']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("musicxml", type=Path)
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    ap.add_argument("--bars", action="store_true", help="list flagged bars per part")
    ap.add_argument("--range", help="restrict to bars A-B, e.g. 1-16")
    ap.add_argument("--check", action="store_true", help="exit 1 on threshold violations")
    a = ap.parse_args(argv)
    rng = tuple(int(x) for x in a.range.split("-")) if a.range else None
    parts, score = parse(a.musicxml)
    results = [analyse_part(p, rng) for p in parts]
    metrics = [r[0] for r in results]
    agg = aggregate(metrics, parts, rng)
    viol = violations(metrics)
    if a.json:
        out = {"file": str(a.musicxml), "range": rng, "score": {**score, "words": score["words"]},
               "aggregate": agg, "parts": metrics, "violations": viol}
        if a.bars:
            out["flagged_bars"] = {m["part"]: r[1] for m, r in zip(metrics, results) if r[1]}
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(md_report(a.musicxml, score, agg, metrics, rng))
        if a.bars:
            print("\nFlagged bars:\n")
            for m, (_, fl) in zip(metrics, results):
                if fl:
                    items = sorted(fl.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
                    print(f"- **{m['part']}**: " + "; ".join(f"{b}: {', '.join(v)}" for b, v in items))
        print("\nThreshold violations:" + ("" if viol else " none"))
        for v in viol:
            print(f"- {v}")
    return 1 if (a.check and viol) else 0


if __name__ == "__main__":
    sys.exit(main())
