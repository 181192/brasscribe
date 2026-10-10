"""Talking score: the text form of a score (docs/accessibility/talking-score-spec.md).

  build(musicxml, composition)  -> TalkingScore JSON shape (spec §6) from the arranged MusicXML
                                   (spelled written pitch, types, ties, tuplets) plus the Composition
                                   (confidence, sources, performed time, free regions)
  announce(part, bar, event, context, settings) -> one announcement string (spec §4)
  to_html / to_text(doc, settings)              -> the export: a heading per part, a sub-heading
                                                   per bar, one line per event (standard verbosity)

The conformance vectors (docs/accessibility/talking-score-vectors.json) are the reference, the
same ones the Windows app's announcer passes. Output never depends on the process locale.
Events are plain dicts with the JSON field names.
"""

from __future__ import annotations

import html
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path

TICKS_PER_QUARTER = 10080  # exact for every tuplet the engine writes
UNCERTAIN_BELOW = 0.7
VERY_UNCERTAIN_BELOW = 0.4
COLOUR_ONLY_CONFIDENCE = 0.55  # a note the MusicXML colours as uncertain, with no Composition match
PICKUP_BAR = 0  # the number of a pickup (anacrusis): spoken as "pickup", never as a bar number (spec §4.10)


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def round_half(x: float) -> float:
    return math.floor(x * 2 + 0.5) / 2


def midi(p: dict) -> int:
    pc = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}.get(p["step"], 0)
    return (p["octave"] + 1) * 12 + pc + p.get("alter", 0)


def concert_key(written_fifths: int, transpose: dict | None) -> int:
    """Key signature in concert pitch: the written key moved by the part's transposition."""
    chrom = (transpose or {}).get("chromatic", 0)
    if chrom % 12 == 0:
        return written_fifths
    shift = (chrom * 7) % 12
    if shift > 6:
        shift -= 12
    k = written_fifths + shift
    return k - 12 if k > 7 else k + 12 if k < -7 else k


SOURCE_NAMES = {"swiftf0": "SwiftF0", "swift-f0": "SwiftF0", "sw": "SwiftF0", "muscriptor": "MuScriptor",
                "mus": "MuScriptor", "basic-pitch": "Basic Pitch", "basicpitch": "Basic Pitch", "bp": "Basic Pitch",
                "mega53": "Mega-53", "mega-53": "Mega-53", "beat-this": "Beat This"}


def source_name(s: str) -> str:
    return SOURCE_NAMES.get(s.lower(), s)


@dataclass(frozen=True)
class Settings:
    lang: str = "en"
    pitch_mode: str = "written"  # written | concert
    verbosity: str = "standard"  # brief | standard | full
    octave_style: str = "scientific"  # scientific | helmholtz (nb)
    announce_confident: bool = False

    @property
    def nb(self) -> bool:
        return self.lang.lower().startswith(("nb", "no"))


@dataclass(frozen=True)
class Context:
    """What the previous announcement left behind; decides which parts get repeated."""
    part: str | None = None
    bar: int | None = None
    pitch_mode: str | None = None


@dataclass(frozen=True)
class Part:
    name: str
    name_nb: str | None = None
    instrument: str | None = None
    instrument_nb: str | None = None
    transpose: dict | None = None


@dataclass(frozen=True)
class Bar:
    number: int
    key_fifths: int = 0
    key_changed: bool = False
    time_changed: dict | None = None
    tempo_marked: float | None = None
    rehearsal: str | None = None
    free_region: dict | None = None
    entering_region: bool = False
    a_tempo: bool = False
    total_bars: int = 0


def _reduce(num: int, den: int) -> tuple[int, int]:
    g = math.gcd(abs(num), abs(den))
    return (num // g, den // g) if g else (num, den)


def _sixths(p: dict, num: int, den: int) -> int | None:
    """In compound time, where the beat is a dotted quarter: the offset in sixths of the beat, when
    it is one. The even sixths are the beat's three eighths, all six its sixteenths; none is a triplet."""
    return num * 6 // den if p.get("compound") and num > 0 and 6 % den == 0 else None


def _key_alters(step: str, fifths: int) -> bool:
    if fifths > 0:
        return step in "FCGDAEB"[:min(fifths, 7)]
    return fifths < 0 and step in "BEADGCF"[:min(-fifths, 7)]


class _Lexicon:
    decimal = "."

    def number(self, x: float) -> str:
        r = math.floor(x * 10 + 0.5) / 10
        if abs(r - round(r)) < 1e-9:
            return str(int(round(r)))
        return f"{r:.1f}".replace(".", self.decimal)

    def join_and(self, items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + f" {self.AND} " + items[-1]

    def dynamic(self, d: str) -> str:
        return {"ppp": "pianississimo", "pp": "pianissimo", "p": "piano", "mp": "mezzo-piano", "mf": "mezzo-forte",
                "f": "forte", "ff": "fortissimo", "fff": "fortississimo", "sfz": "sforzando", "fp": "forte-piano"}.get(d, d)


class _En(_Lexicon):
    OF, HELD, FROM, AND = " of ", "held", "from ", "and"
    PICKUP, REST = "pickup", "rest"
    REST_WHOLE_BAR, UNCERTAIN, VERY_UNCERTAIN, CONFIDENT = "rest, whole bar", "uncertain", "very uncertain", "confident"
    CONCERT_PITCH, WRITTEN_PITCH = "Concert pitch", "Written pitch"
    TYPES = {"breve": ("double whole note", "double whole"), "whole": ("whole note", "whole"), "half": ("half note", "half"),
             "quarter": ("quarter note", "quarter"), "eighth": ("eighth note", "eighth"), "16th": ("sixteenth note", "sixteenth"),
             "32nd": ("thirty-second note", "thirty-second"), "64th": ("sixty-fourth note", "sixty-fourth")}
    DOTS = {0: "", 1: "dotted ", 2: "double-dotted "}
    ARTICULATIONS = {"strong-accent": "marcato", "trill": "trill", "trill-sharp": "trill with sharp",
                     "trill-flat": "trill with flat", "trill-natural": "trill with natural",
                     "trill-double-sharp": "trill with double sharp", "trill-flat-flat": "trill with double flat"}

    def bar(self, n): return self.PICKUP if n == PICKUP_BAR else f"bar {n}"
    def bars_range(self, a, b): return f"bars {a} to {b}"
    def rest_bars(self, n): return f"rest, {n} bars"
    def position(self, p): return "beat " + self.position_brief(p)

    def position_brief(self, p):
        num, den = _reduce(p.get("num", 0), p.get("den", 1))
        b = p["beat"]
        k = _sixths(p, num, den)
        if k is not None:
            return f"{b}, eighth {k // 2 + 1}" if k % 2 == 0 else f"{b}, sixteenth {k + 1}"
        return {(1, 2): f"{b} and", (1, 4): f"{b} e", (3, 4): f"{b} a", (1, 3): f"{b}, triplet 2",
                (2, 3): f"{b}, triplet 3"}.get((num, den), f"{b}" if num == 0 else f"{b} plus {num}/{den}")

    def pitch(self, p, key, style):
        alter = p.get("alter", 0)
        acc = {2: "-double-sharp", 1: "-sharp", -1: "-flat", -2: "-double-flat"}.get(alter, "")
        if alter == 0 and _key_alters(p["step"], key):
            acc = "-natural"
        return f"{p['step']}{acc} {p['octave']}"

    def duration(self, t, dots, brief):
        return self.DOTS.get(dots, "triple-dotted ") + self.TYPES.get(t, (t, t))[1 if brief else 0]

    def rest(self, t, dots, brief):
        return self.DOTS.get(dots, "triple-dotted ") + self.TYPES.get(t, (t, t))[1] + " rest"

    def chord(self, n): return f"chord, {n} notes"
    def tied_to(self, d, bar): return f"tied to {d}" if bar is None else f"tied to {d} in bar {bar}"

    def tied_chain(self, beats):
        whole = math.floor(beats)
        b = f"{whole} and a half" if abs(beats - whole - 0.5) < 1e-9 else self.number(beats)
        return f"tied, {b} beats in all"

    def tuplet(self, t):
        if t["actual"] == 3 and t["normal"] == 2:
            return f"triplet, {t['index']} of 3"
        return f"{t['actual']} in the time of {t['normal']}, {t['index']} of {t['actual']}"

    def articulation(self, a): return self.ARTICULATIONS.get(a, a)
    def held_about(self, s): return f"held about {self.number(s)} {'second' if s == 1 else 'seconds'}"

    def at_time(self, seconds):
        s = round_half_up(seconds)
        if s < 60:
            return f"at {s} {'second' if s == 1 else 'seconds'}"
        m, r = divmod(s, 60)
        return f"at {m} {'minute' if m == 1 else 'minutes'} {r} {'second' if r == 1 else 'seconds'}"

    def ad_lib(self, a, b, s):
        bars = f"bars {a} to {b}" if a != PICKUP_BAR else "pickup" if b == PICKUP_BAR else f"pickup to bar {b}"
        return f"Ad lib, free time, {bars}, about {s} seconds"

    def a_tempo(self, bpm): return f"A tempo, {bpm} beats per minute"

    def key(self, f):
        if f == 0:
            return "no sharps or flats"
        n = abs(f)
        return f"key {n} {'sharp' if f > 0 else 'flat'}{'' if n == 1 else 's'}"

    def time(self, t): return f"{t['beats']} {t['beat_type']} time"
    def tempo(self, bpm): return f"tempo {bpm}"
    def rehearsal(self, m): return f"rehearsal {m}"
    def confidence_percent(self, p): return f"confidence {p} percent"
    def sources(self, names): return ("source " if len(names) == 1 else "sources ") + self.join_and(names)
    def written_sounds(self, w, s): return f"written {w}, sounds {s}"
    def instrument_name(self, i): return i.replace("♭", "-flat").replace("♯", "-sharp")
    def part_heading(self, n): return n

    def bar_heading(self, a, b=None):
        if a == PICKUP_BAR:
            return "Pickup" if b is None else "Pickup and bar 1" if b == 1 else f"Pickup and bars 1–{b}"
        return f"Bar {a}" if b is None else f"Bars {a}–{b}"


class _Nb(_Lexicon):
    decimal = ","
    OF, HELD, FROM, AND = " av ", "holdes", "fra ", "og"
    PICKUP, REST = "opptakt", "pause"
    REST_WHOLE_BAR, UNCERTAIN, VERY_UNCERTAIN, CONFIDENT = "pause hele takten", "usikker", "svært usikker", "sikker"
    CONCERT_PITCH, WRITTEN_PITCH = "Klingende tone", "Skrevet tone"
    TYPES = {"breve": ("brevis", "brevis"), "whole": ("helnote", "hel"), "half": ("halvnote", "halv"),
             "quarter": ("fjerdedelsnote", "fjerdedel"), "eighth": ("åttendedelsnote", "åttendedel"),
             "16th": ("sekstendedelsnote", "sekstendedel"), "32nd": ("trettitodelsnote", "trettitodel"),
             "64th": ("sekstifiredelsnote", "sekstifiredel")}
    RESTS = {"breve": "brevispause", "whole": "helpause", "half": "halvpause", "quarter": "fjerdedelspause",
             "eighth": "åttendedelspause", "16th": "sekstendedelspause", "32nd": "trettitodelspause",
             "64th": "sekstifiredelspause"}
    DOTS = {0: "", 1: "punktert ", 2: "dobbeltpunktert "}
    ARTICULATIONS = {"fermata": "fermat", "accent": "aksent", "strong-accent": "marcato", "trill": "trille",
                     "trill-sharp": "trille med kryss", "trill-flat": "trille med b",
                     "trill-natural": "trille med oppløsningstegn", "trill-double-sharp": "trille med dobbeltkryss",
                     "trill-flat-flat": "trille med dobbelt-b"}

    def bar(self, n): return self.PICKUP if n == PICKUP_BAR else f"takt {n}"
    def bars_range(self, a, b): return f"takt {a} til {b}"
    def rest_bars(self, n): return f"pause, {n} takter"
    def position(self, p): return "slag " + self.position_brief(p)

    def position_brief(self, p):
        num, den = _reduce(p.get("num", 0), p.get("den", 1))
        b = p["beat"]
        k = _sixths(p, num, den)
        if k is not None:
            return f"{b}, {k // 2 + 1}. åttendedel" if k % 2 == 0 else f"{b}, {k + 1}. sekstendedel"
        return {(1, 2): f"{b}-og", (1, 4): f"{b}, 2. av 4", (3, 4): f"{b}, 4. av 4", (1, 3): f"{b}, triol 2",
                (2, 3): f"{b}, triol 3"}.get((num, den), f"{b}" if num == 0 else f"{b} pluss {num}/{den}")

    @staticmethod
    def name(step, alter):
        letter = "H" if step == "B" else step
        special = {("B", -1): "B", ("E", -1): "Ess", ("A", -1): "Ass"}
        if (step, alter) in special:
            return special[(step, alter)]
        return {-1: letter + "ess", 1: letter + "iss", 2: letter + " dobbeltkryss", -2: letter + " dobbelt-b"}.get(alter, letter)

    def pitch(self, p, key, style):
        name = self.name(p["step"], p.get("alter", 0))
        if style == "helmholtz":
            low, o = name.lower(), p["octave"]
            return {2: f"store {name}", 3: f"lille {low}", 4: f"enstrøken {low}", 5: f"tostrøken {low}",
                    6: f"trestrøken {low}"}.get(o, f"kontra {name}" if o <= 1 else f"{low} {o}")
        return f"{name} {p['octave']}"

    def duration(self, t, dots, brief):
        return self.DOTS.get(dots, "trippelpunktert ") + self.TYPES.get(t, (t, t))[1 if brief else 0]

    def rest(self, t, dots, brief):
        return self.DOTS.get(dots, "trippelpunktert ") + self.RESTS.get(t, t + " pause")

    def chord(self, n): return f"akkord, {n} toner"
    def tied_to(self, d, bar): return f"bundet til {d}" if bar is None else f"bundet til {d} i takt {bar}"

    def tied_chain(self, beats):
        whole = math.floor(beats)
        b = f"{whole} og et halvt" if abs(beats - whole - 0.5) < 1e-9 else self.number(beats)
        return f"bundet, {b} slag i alt"

    def tuplet(self, t):
        if t["actual"] == 3 and t["normal"] == 2:
            return f"triol, {t['index']} av 3"
        return f"{t['actual']} på {t['normal']}, {t['index']} av {t['actual']}"

    def articulation(self, a): return self.ARTICULATIONS.get(a, a)
    def held_about(self, s): return f"holdes omtrent {self.number(s)} {'sekund' if s == 1 else 'sekunder'}"

    def at_time(self, seconds):
        s = round_half_up(seconds)
        if s < 60:
            return f"ved {s} {'sekund' if s == 1 else 'sekunder'}"
        m, r = divmod(s, 60)
        return f"ved {m} {'minutt' if m == 1 else 'minutter'} {r} {'sekund' if r == 1 else 'sekunder'}"

    def ad_lib(self, a, b, s):
        bars = f"takt {a} til {b}" if a != PICKUP_BAR else "opptakt" if b == PICKUP_BAR else f"opptakt til takt {b}"
        return f"Ad lib, fritt tempo, {bars}, omtrent {s} sekunder"

    def a_tempo(self, bpm): return f"A tempo, {bpm} slag per minutt"
    def key(self, f): return "ingen faste fortegn" if f == 0 else f"{f} kryss" if f > 0 else f"{-f} b"

    def time(self, t):
        unit = {1: "hel", 2: "halvdels", 4: "fjerdedels", 8: "åttendedels", 16: "sekstendedels"}.get(
            t["beat_type"], f"{t['beat_type']}-dels")
        return f"{t['beats']} {unit} takt"

    def tempo(self, bpm): return f"tempo {bpm}"
    def rehearsal(self, m): return f"øvingsbokstav {m}"
    def confidence_percent(self, p): return f"sikkerhet {p} prosent"
    def sources(self, names): return ("kilde " if len(names) == 1 else "kilder ") + self.join_and(names)
    def written_sounds(self, w, s): return f"skrevet {w}, klinger {s}"
    def instrument_name(self, i): return i
    def part_heading(self, n): return n

    def bar_heading(self, a, b=None):
        if a == PICKUP_BAR:
            return "Opptakt" if b is None else "Opptakt og takt 1" if b == 1 else f"Opptakt og takt 1–{b}"
        return f"Takt {a}" if b is None else f"Takt {a}–{b}"


EN, NB = _En(), _Nb()


def _lex(s: Settings) -> _Lexicon:
    return NB if s.nb else EN


def _bar_changes(bar: Bar, L) -> list[str]:
    out = []
    if bar.key_changed:
        out.append(L.key(bar.key_fifths))
    if bar.time_changed:
        out.append(L.time(bar.time_changed))
    if bar.tempo_marked is not None and not bar.a_tempo:
        out.append(L.tempo(round_half_up(bar.tempo_marked)))
    if bar.rehearsal:
        out.append(L.rehearsal(bar.rehearsal))
    return out


def announce(part: Part, bar: Bar, ev: dict, ctx: Context, s: Settings, by_bar: bool = False) -> str:
    L = _lex(s)
    kind = ev.get("kind", "note")
    if kind == "mode-change":
        if s.pitch_mode == "concert":
            return L.CONCERT_PITCH
        inst = (part.instrument_nb or part.instrument) if s.nb else part.instrument
        return L.WRITTEN_PITCH if inst is None else L.WRITTEN_PITCH + ", " + L.instrument_name(inst)

    out = []
    region = bar.free_region
    if region and bar.entering_region:
        out.append(L.ad_lib(region["start_bar"], region["end_bar"], round_half_up(region["end_s"] - region["start_s"])) + ". ")
    elif bar.a_tempo and bar.tempo_marked is not None:
        out.append(L.a_tempo(round_half_up(bar.tempo_marked)) + ". ")

    part_changed = ctx.part is not None and ctx.part != part.name
    if part_changed:
        out.append(((part.name_nb or part.name) if s.nb else part.name) + ". ")
        bar = replace(bar, key_changed=True)  # §4.9: the new part's key is always announced

    in_free = bool(region) and region.get("notation", "proportional") == "proportional" and ev.get("time_s") is not None
    changes = _bar_changes(bar, L)
    show_bar = (s.verbosity == "full" or by_bar or ctx.bar != bar.number or part_changed or bool(changes)
                or kind == "bar-rest")

    if kind == "bar-rest":
        n = ev.get("bars", 1)
        if bar.number == PICKUP_BAR:  # §4.10: the pickup is named, and is not one of the bars counted
            after = n - 1
            where = L.PICKUP if after <= 0 else f"{L.PICKUP} {L.AND} " + (L.bar(1) if after == 1 else L.bars_range(1, after))
            out.append(where + ": " + (L.rest_bars(after) if after > 1 else L.REST))
        else:
            out.append(L.bars_range(bar.number, bar.number + n - 1) + ": " + L.rest_bars(n) if n > 1
                       else L.bar(bar.number) + ": " + L.REST_WHOLE_BAR)
        return "".join(out)

    brief = s.verbosity == "brief"
    if not brief and show_bar:
        out.append(L.bar(bar.number))
        if s.verbosity == "full" and bar.total_bars > 0 and bar.number != PICKUP_BAR:
            out.append(L.OF + str(bar.total_bars))
        for c in changes:
            out.append(", " + c)
        out.append(", ")

    if in_free:
        out.append(L.at_time(ev["time_s"]))
    elif ev.get("pos"):
        out.append(L.position_brief(ev["pos"]) if brief else L.position(ev["pos"]))
    out.append(": ")

    key = concert_key(bar.key_fifths, part.transpose) if s.pitch_mode == "concert" else bar.key_fifths

    def pitch_of(e):
        p = (e.get("concert") or e.get("written")) if s.pitch_mode == "concert" else (e.get("written") or e.get("concert"))
        return "" if p is None else L.pitch(p, key, s.octave_style)

    typ, dots = ev.get("type") or "quarter", ev.get("dots", 0)
    if kind == "held":
        out.append(pitch_of(ev) + " " + L.HELD + ", " + L.FROM)
        f = ev.get("held_from")
        if f:
            if f["bar"] != bar.number:
                out.append(L.bar(f["bar"]) + " ")
            out.append(L.position({k: v for k, v in f.items() if k != "bar"}))
        return "".join(out)
    if kind == "rest":
        out.append(L.rest(typ, dots, brief))
    elif kind == "chord":
        field_ = "concert" if s.pitch_mode == "concert" else "written"
        ps = sorted((cp[field_] for cp in ev.get("pitches", [])), key=midi)
        names = [L.pitch(p, key, s.octave_style) for p in ps]
        out.append(L.chord(len(names)) + ": " + ", ".join(names) + ", " + L.duration(typ, dots, brief))
    elif kind == "unpitched":
        names = (ev.get("instruments_nb") or ev.get("instruments")) if s.nb else ev.get("instruments")
        out.append(L.join_and(list(names or [])) + ", " + L.duration(typ, dots, brief))
    else:
        if s.verbosity == "full" and ev.get("written") and ev.get("concert"):
            wk, ck = bar.key_fifths, concert_key(bar.key_fifths, part.transpose)
            out.append(L.written_sounds(L.pitch(ev["written"], wk, s.octave_style), L.pitch(ev["concert"], ck, s.octave_style)))
        else:
            out.append(pitch_of(ev))
        out.append((" " if brief else ", ") + L.duration(typ, dots, brief))

    mods = []
    tie = ev.get("tie")
    if tie and tie.get("start"):
        if tie.get("chain_beats") is not None:
            mods.append(L.tied_chain(tie["chain_beats"]))
        elif tie.get("next"):
            nx = tie["next"]
            mods.append(L.tied_to(L.duration(nx["type"], nx.get("dots", 0), False), nx["bar"] if nx["bar"] != bar.number else None))
    if ev.get("tuplet"):
        mods.append(L.tuplet(ev["tuplet"]))
    mods += [L.articulation(a) for a in ev.get("articulations") or []]
    if ev.get("dynamic"):
        mods.append(L.dynamic(ev["dynamic"]))
    if region and (ev.get("performed_s") or 0) >= 1.0:
        mods.append(L.held_about(round_half(ev["performed_s"])))
    conf = ev.get("confidence")
    if conf is not None and not ev.get("checked"):
        level = "very" if conf < VERY_UNCERTAIN_BELOW else "uncertain" if conf < UNCERTAIN_BELOW else "confident"
        if level == "very":
            mods.append(L.VERY_UNCERTAIN)
        elif level == "uncertain":
            mods.append(L.UNCERTAIN)
        elif s.verbosity == "full" and s.announce_confident:
            mods.append(L.CONFIDENT)
        if s.verbosity == "full" and (level != "confident" or s.announce_confident):
            mods.append(L.confidence_percent(round_half_up(conf * 100)))
            if ev.get("sources"):
                mods.append(L.sources([source_name(x) for x in ev["sources"]]))
    out += [", " + m for m in mods]
    return "".join(out)


# --------------------------------------------------------------------------- build from MusicXML

NB_PART_NAMES = {
    "Soprano Cornet": "Sopran-kornett", "Solo Cornet": "Solokornett", "Repiano Cornet": "Repiano-kornett",
    "1st Cornet": "1. kornett", "Tenor Horn": "Althorn",
    "2nd Cornet": "2. kornett", "3rd Cornet": "3. kornett", "Flugelhorn": "Flygelhorn", "Solo Horn": "Solo althorn",
    "1st Horn": "1. althorn", "2nd Horn": "2. althorn", "1st Baritone": "1. baryton", "2nd Baritone": "2. baryton",
    "1st Trombone": "1. trombone", "2nd Trombone": "2. trombone", "Bass Trombone": "Basstrombone",
    "Euphonium": "Eufonium", "E♭ Bass": "Ess-bass", "B♭ Bass": "B-bass", "Percussion": "Slagverk",
    "Trumpet": "Trompet",
}


def instrument_nb(en: str) -> str:
    s = en
    for a, b in (("Soprano Cornet", "sopran-kornett"), ("Cornet", "kornett"), ("Trumpet", "trompet"), ("Flugelhorn", "flygelhorn"),
                 ("Tenor Horn", "althorn"), ("Horn", "althorn"), ("Baritone", "baryton"), ("Euphonium", "eufonium"),
                 ("Bass Trombone", "basstrombone"), ("Drum Kit", "trommesett"),
                 (" in B♭", " i B"), (" in E♭", " i Ess"), (" in C", " i C")):
        s = s.replace(a, b)
    return s[:1].lower() + s[1:]


def drum(step: str, octave: int, notehead: str | None) -> tuple[str, str]:
    x = notehead == "x"
    if (step, octave) in (("F", 4), ("E", 4)):
        return "bass drum", "stortromme"
    if (step, octave) == ("C", 5):
        return "snare drum", "skarptromme"
    table = {("G", 5): ("hi-hat", "hi-hat"), ("A", 5): ("crash cymbal", "crashcymbal"),
             ("F", 5): ("ride cymbal", "ridecymbal"), ("D", 4): ("pedal hi-hat", "pedal-hi-hat")}
    if x and (step, octave) in table:
        return table[(step, octave)]
    if (step, octave) in (("E", 5), ("D", 5)):
        return "tom", "tom"
    if (step, octave) == ("A", 4):
        return "floor tom", "gulvtom"
    return "drum", "tromme"


def to_concert(written: dict, t: dict) -> dict:
    """Concert pitch keeping the diatonic spelling: written + chromatic semitones and diatonic steps."""
    steps = "CDEFGAB"
    diatonic = t.get("diatonic", 0) + 7 * t.get("octave", 0)
    chromatic = t.get("chromatic", 0) + 12 * t.get("octave", 0)
    abs_step = written["octave"] * 7 + steps.index(written["step"]) + diatonic
    octave, rem = divmod(abs_step, 7)
    target = {"step": steps[rem], "alter": 0, "octave": octave}
    target["alter"] = midi(written) + chromatic - midi(target)
    return target


def position(offset: int, divisions: int, time: dict) -> dict:
    compound = time["beat_type"] == 8 and time["beats"] % 3 == 0 and time["beats"] > 3
    beat_div = divisions * 4 // time["beat_type"] * (3 if compound else 1)
    if beat_div <= 0:
        return {"beat": 1, "num": 0, "den": 1}
    beat, rem = divmod(offset, beat_div)
    f = Fraction(rem, beat_div)
    pos = {"beat": beat + 1, "num": f.numerator, "den": f.denominator}
    return {**pos, "compound": True} if compound else pos


def _type_from_duration(dur: int, divisions: int) -> str:
    q = dur / divisions
    for limit, t in ((8, "breve"), (4, "whole"), (2, "half"), (1, "quarter"), (0.5, "eighth"), (0.25, "16th"), (0.125, "32nd")):
        if q >= limit:
            return t
    return "64th"


def _int(el, default=0):
    try:
        return int(el.text) if el is not None and el.text is not None else default
    except ValueError:
        return default


def _has_tie(note, kind: str) -> bool:
    return any(t.get("type") == kind for t in note.findall("tie")) or \
        any(t.get("type") == kind for t in note.findall("notations/tied"))


class _Matcher:
    """The Composition note behind a printed note: same onset tick and concert pitch, else the same pitch class."""

    def __init__(self, comp: dict):
        self.tpb = comp.get("ticks_per_beat", 24)
        self.by_onset: dict[int, list[dict]] = {}
        for v in comp.get("voices", []):
            if v.get("layer") == "drums" or v.get("role") == "rhythm":
                continue
            for n in v.get("notes", []):
                self.by_onset.setdefault(n["start"], []).append(n)

    def match(self, quarter: float, pitch: int) -> dict | None:
        tick = round_half_up(quarter * self.tpb)
        for t in (tick, tick - 1, tick + 1):
            cands = self.by_onset.get(t, [])
            hit = next((n for n in cands if n["pitch"] == pitch), None) or \
                next((n for n in cands if (n["pitch"] - pitch) % 12 == 0), None)
            if hit:
                return hit
        return None


def seconds_at(comp: dict, tick: float) -> float:
    tpb = comp.get("ticks_per_beat", 24)
    bt = comp.get("beat_times") or []
    beat = comp.get("first_downbeat", 0) + tick / tpb
    if not bt:
        return beat * 0.5
    if len(bt) == 1:
        return bt[0] + beat * 0.5
    i = min(max(math.floor(beat), 0), len(bt) - 2)
    return bt[i] + (beat - i) * (bt[i + 1] - bt[i])


def build(musicxml: str | Path, composition: dict | None = None) -> dict:
    """TalkingScore document (spec §6) from partwise MusicXML text or file, plus the Composition when known."""
    text = Path(musicxml).read_text() if isinstance(musicxml, Path) else musicxml
    root = ET.fromstring(text.encode() if isinstance(text, str) else text)
    if root.tag != "score-partwise":
        raise ValueError("only score-partwise MusicXML is supported")
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    info = {sp.get("id"): (sp.findtext("part-name") or "Part", sp.findtext("score-instrument/instrument-name"))
            for sp in root.findall("part-list/score-part")}
    matcher = _Matcher(composition) if composition else None
    measure_starts: list[float] = []
    parts = []
    for pi, part_el in enumerate(root.findall("part")):
        name, inst = info.get(part_el.get("id"), ("Part", None))
        part = {"id": part_el.get("id"), "name": name, "name_nb": NB_PART_NAMES.get(name, name), "instrument": inst,
                "instrument_nb": instrument_nb(inst) if inst else None,
                "transpose": {"chromatic": 0, "diatonic": 0, "octave": 0}, "percussion": False, "bars": []}
        divisions, fifths, time = 1, 0, {"beats": 4, "beat_type": 4}
        part_q = 0.0
        tuplet_count = 0
        pending: list[tuple[dict, int, int]] = []  # (tie-start event, concert MIDI, bar number)
        chains: dict[int, dict] = {}  # id(event) -> {"head", "length", "count"}
        for idx, m in enumerate(part_el.findall("measure")):
            try:
                number = int(m.get("number"))
            except (TypeError, ValueError):
                number = idx + 1
            # A pickup: the first measure, numbered 0 or left out of the numbering. Its notes are placed on the
            # beats they fall on in the bar they lead into.
            lead = 0
            if idx == 0 and (number == PICKUP_BAR or m.get("implicit") == "yes"):
                number, lead = PICKUP_BAR, _lead_in(m, divisions, time)
            tempo = rehearsal = pending_dyn = None
            offset = length = 0
            last = None
            if pi == 0:
                measure_starts.append(part_q)
            bar = {"number": number, "events": []}
            for el in m:
                tag = el.tag
                if tag == "attributes":
                    divisions = _int(el.find("divisions"), divisions)
                    fifths = _int(el.find("key/fifths"), fifths)
                    if el.find("time") is not None:
                        time = {"beats": _int(el.find("time/beats"), 4), "beat_type": _int(el.find("time/beat-type"), 4)}
                    tr = el.find("transpose")
                    if tr is not None:
                        part["transpose"] = {"chromatic": _int(tr.find("chromatic")), "diatonic": _int(tr.find("diatonic")),
                                             "octave": _int(tr.find("octave-change"))}
                    if el.findtext("clef/sign") == "percussion":
                        part["percussion"] = True
                elif tag == "direction":
                    snd = next((s for s in el.iter("sound") if s.get("tempo")), None)
                    if snd is not None:
                        tempo = float(snd.get("tempo"))
                    rh = next(el.iter("rehearsal"), None)
                    if rh is not None and rh.text:
                        rehearsal = rh.text.strip()
                    dyn = next(el.iter("dynamics"), None)
                    if dyn is not None and len(dyn):
                        pending_dyn = dyn[0].tag
                elif tag == "backup":
                    offset -= _int(el.find("duration"))
                elif tag == "forward":
                    offset += _int(el.find("duration"))
                    length = max(length, offset)
                elif tag == "note":
                    dur = _int(el.find("duration"))
                    is_chord, grace = el.find("chord") is not None, el.find("grace") is not None
                    voice = el.findtext("voice") or "1"
                    if is_chord and last is not None:
                        _add_chord_tone(last, el, part)
                        continue
                    start = offset
                    if not grace:
                        offset += dur
                    length = max(length, offset)
                    if grace or voice != "1":
                        if voice != "1":
                            last = None
                        continue
                    ev, tuplet_count = _read_note(el, start, dur, divisions, time, part, tuplet_count, lead)
                    if ev is None:
                        continue
                    if pending_dyn and ev["kind"] not in ("rest", "bar-rest"):
                        ev["dynamic"], pending_dyn = pending_dyn, None
                    abs_q = part_q + start / divisions
                    if ev["kind"] == "rest" and composition:
                        ev["time_s"] = seconds_at(composition, abs_q * composition.get("ticks_per_beat", 24))
                    if ev.get("concert"):
                        mp = midi(ev["concert"])
                        hit = matcher.match(abs_q, mp) if matcher else None
                        if hit:
                            ev["confidence"] = hit.get("confidence")
                            ev["sources"] = list(hit.get("sources", []))
                            if hit.get("onset_s") is not None:
                                ev["time_s"] = hit["onset_s"]
                                if hit.get("offset_s") is not None:
                                    ev["performed_s"] = hit["offset_s"] - hit["onset_s"]
                            for a in hit.get("articulations") or []:
                                if a not in ev["articulations"]:
                                    ev["articulations"].append(a)
                        elif el.get("color") or (el.find("notehead") is not None and el.find("notehead").get("color")):
                            ev["confidence"] = COLOUR_ONLY_CONFIDENCE
                        if ev.get("time_s") is None and composition:
                            ev["time_s"] = seconds_at(composition, abs_q * composition.get("ticks_per_beat", 24))
                        if _has_tie(el, "stop"):
                            i = next((k for k, (_, pm, _) in enumerate(pending) if pm == mp), None)
                            if i is not None:
                                frm, _, frm_bar = pending.pop(i)
                                frm["tie"] = {**(frm.get("tie") or {"start": True}),
                                              "next": {"bar": number, "type": ev["type"], "dots": ev["dots"]}}
                                ev["tie"] = {"stop": True, "start": _has_tie(el, "start")}
                                head = chains.get(id(frm), {"head": frm, "bar": frm_bar})
                                ev["held_from"] = {"bar": head.get("bar", frm_bar), **head["head"]["pos"]}
                                chain = chains.setdefault(id(frm), {"head": frm, "bar": frm_bar, "length": frm["dur_ticks"],
                                                                    "count": 1})
                                chain["length"] += ev["dur_ticks"]
                                chain["count"] += 1
                                chains[id(ev)] = chain
                        if _has_tie(el, "start"):
                            ev["tie"] = {**(ev.get("tie") or {}), "start": True}
                            pending.append((ev, mp, number))
                            chains.setdefault(id(ev), {"head": ev, "bar": number, "length": ev["dur_ticks"], "count": 1})
                    bar["events"].append(ev)
                    last = ev
            bar.update(key_fifths=fifths, time=dict(time), tempo_bpm=tempo, rehearsal=rehearsal)
            part["bars"].append(bar)
            part_q += length / divisions if length > 0 else 4.0 * time["beats"] / time["beat_type"]
        seen = set()
        for chain in chains.values():
            if id(chain) in seen:
                continue
            seen.add(id(chain))
            if chain["count"] > 2 and chain["head"].get("tie"):
                chain["head"]["tie"]["chain_beats"] = chain["length"] / TICKS_PER_QUARTER
        parts.append(part)

    # Tempo marks are global but usually written in one part only: share them with every part.
    for b in range(len(parts[0]["bars"]) if parts else 0):
        tempo = next((p["bars"][b]["tempo_bpm"] for p in parts if b < len(p["bars"]) and p["bars"][b]["tempo_bpm"]), None)
        if tempo:
            for p in parts:
                if b < len(p["bars"]) and p["bars"][b]["tempo_bpm"] is None:
                    p["bars"][b]["tempo_bpm"] = tempo

    # The pickup is not one of the bars counted.
    doc = {"version": 1, "title": title,
           "total_bars": max((sum(b["number"] != PICKUP_BAR for b in p["bars"]) for p in parts), default=0),
           "free_regions": [], "parts": parts}
    if composition and parts:
        doc["free_regions"] = _free_regions(composition, measure_starts, parts[0])
    return doc


def _lead_in(m, divisions: int, time: dict) -> int:
    """What a pickup measure lacks of a full bar, in divisions: 0 when it is a full bar or empty."""
    offset = length = 0
    for el in m:
        if el.tag == "attributes":
            divisions = _int(el.find("divisions"), divisions)
            if el.find("time") is not None:
                time = {"beats": _int(el.find("time/beats"), 4), "beat_type": _int(el.find("time/beat-type"), 4)}
        elif el.tag == "backup":
            offset -= _int(el.find("duration"))
        elif el.tag == "forward" or (el.tag == "note" and el.find("chord") is None and el.find("grace") is None):
            offset += _int(el.find("duration"))
            length = max(length, offset)
    full = divisions * 4 * time["beats"] // time["beat_type"] if time["beat_type"] > 0 else 0
    return full - length if 0 < length < full else 0


def _read_note(el, start, dur, divisions, time, part, tuplet_count, lead=0):
    """`lead`: the divisions a pickup lacks of a full bar; `pos` counts from where that bar would start."""
    ev = {"kind": "note", "tick": start * TICKS_PER_QUARTER // divisions, "dur_ticks": dur * TICKS_PER_QUARTER // divisions,
          "pos": position(start + lead, divisions, time), "type": el.findtext("type"), "dots": len(el.findall("dot")),
          "tuplet": None, "tie": None, "articulations": [], "dynamic": None, "confidence": None, "sources": [],
          "checked": False, "time_s": None, "performed_s": None}
    rest = el.find("rest")
    if rest is not None:
        if rest.get("measure") == "yes" or (ev["type"] is None and start == 0):
            ev["kind"], ev["pos"], ev["bars"] = "bar-rest", position(0, divisions, time), 1
        else:
            ev["kind"] = "rest"
        ev["type"] = ev["type"] or _type_from_duration(dur, divisions)
        return ev, tuplet_count
    ev["type"] = ev["type"] or _type_from_duration(dur, divisions)
    tm = el.find("time-modification")
    if tm is not None:
        actual, normal = _int(tm.find("actual-notes"), 3), _int(tm.find("normal-notes"), 2)
        ev["tuplet"] = {"actual": actual, "normal": normal, "index": tuplet_count % actual + 1}
        tuplet_count += 1
    else:
        tuplet_count = 0
    nots = el.find("notations")
    if nots is not None:
        ev["articulations"] += [a.tag for a in (nots.find("articulations") if nots.find("articulations") is not None else [])]
        orn = nots.find("ornaments")
        if orn is not None and orn.find("trill-mark") is not None:
            mark = (orn.findtext("accidental-mark") or "").strip()
            ev["articulations"].append(f"trill-{mark}" if mark else "trill")
        if nots.find("fermata") is not None:
            ev["articulations"].append("fermata")
        d = nots.find("dynamics")
        if d is not None and len(d):
            ev["dynamic"] = d[0].tag
    up = el.find("unpitched")
    if up is not None:
        en, nb = drum(up.findtext("display-step") or "C", _int(up.find("display-octave"), 5), el.findtext("notehead"))
        ev.update(kind="unpitched", instruments=[en], instruments_nb=[nb])
        return ev, tuplet_count
    p = el.find("pitch")
    if p is None:
        return None, tuplet_count
    written = {"step": p.findtext("step") or "C", "alter": _int(p.find("alter")), "octave": _int(p.find("octave"), 4)}
    ev["written"] = written
    ev["concert"] = dict(written) if part["percussion"] else to_concert(written, part["transpose"])
    nh = el.find("notehead")
    if nh is not None and nh.get("parentheses") == "yes" and ev["confidence"] is None:
        ev["confidence"] = 0.3
    return ev, tuplet_count


def _add_chord_tone(head: dict, el, part: dict) -> None:
    up = el.find("unpitched")
    if up is not None:
        en, nb = drum(up.findtext("display-step") or "C", _int(up.find("display-octave"), 5), el.findtext("notehead"))
        if head.get("instruments") is not None and en not in head["instruments"]:
            head["instruments"].append(en)
        if head.get("instruments_nb") is not None and nb not in head["instruments_nb"]:
            head["instruments_nb"].append(nb)
        return
    p = el.find("pitch")
    if p is None or head.get("written") is None:
        return
    written = {"step": p.findtext("step") or "C", "alter": _int(p.find("alter")), "octave": _int(p.find("octave"), 4)}
    if head["kind"] == "note":
        head["kind"] = "chord"
        head["pitches"] = [{"written": head["written"], "concert": head.get("concert") or head["written"]}]
    head["pitches"].append({"written": written, "concert": dict(written) if part["percussion"] else to_concert(written, part["transpose"])})


def _free_regions(comp: dict, measure_starts: list[float], part: dict) -> list[dict]:
    tpb = comp.get("ticks_per_beat", 24)
    bars = part["bars"]

    def bar_at(q):
        i = max((k for k, s in enumerate(measure_starts) if s <= q + 1e-9), default=0)
        return bars[min(max(i, 0), len(bars) - 1)]["number"]

    out = []
    for r in comp.get("free_regions") or []:
        sq, eq = r["start"] / tpb, r["end"] / tpb
        out.append({"start_bar": bar_at(sq), "end_bar": bar_at(max(sq, eq - 1e-6)), "start_s": r.get("start_s", 0.0),
                    "end_s": r.get("end_s", 0.0), "tempo_bpm": r.get("tempo_bpm"),
                    "notation": r.get("notation", "proportional"), "label": r.get("label", "ad lib.")})
    return out


# --------------------------------------------------------------------------- walk and export

def _region_at(doc: dict, bar: int) -> dict | None:
    return next((r for r in doc["free_regions"] if r["start_bar"] <= bar <= r["end_bar"]), None)


def _is_tie_continuation(ev: dict) -> bool:
    return bool((ev.get("tie") or {}).get("stop"))


def _is_rest_bar(bar: dict) -> bool:
    return len(bar["events"]) == 1 and bar["events"][0]["kind"] == "bar-rest"


def part_lines(doc: dict, part_index: int, s: Settings) -> list[tuple[str, list[str]]]:
    """(bar heading, announcements) for every bar of a part, walking note by note as a reader would."""
    p = doc["parts"][part_index]
    L = _lex(s)
    ap = Part(p["name"], p.get("name_nb"), p.get("instrument"), p.get("instrument_nb"), p.get("transpose"))
    ctx = Context()
    out: list[tuple[str, list[str]]] = []
    bars = p["bars"]
    b = 0
    while b < len(bars):
        bar = bars[b]
        prev = bars[b - 1] if b else None
        region = _region_at(doc, bar["number"])
        prev_region = _region_at(doc, ctx.bar) if ctx.bar is not None else None
        entering = region is not None and region is not prev_region
        a_tempo = region is None and prev_region is not None
        tempo = bar.get("tempo_bpm")
        if region is not None and region.get("notation", "proportional") == "proportional":
            tempo = None
        if a_tempo:
            tempo = tempo or next((x["tempo_bpm"] for x in reversed(bars[:b])
                                   if x.get("tempo_bpm") and _region_at(doc, x["number"]) is None), None)
        elif tempo is not None and prev is not None:
            eff = next((x["tempo_bpm"] for x in reversed(bars[:b]) if x.get("tempo_bpm")), None)
            if eff == tempo:
                tempo = None
        abar = Bar(bar["number"], bar.get("key_fifths", 0),
                   key_changed=prev is not None and prev.get("key_fifths") != bar.get("key_fifths"),
                   time_changed=bar["time"] if prev is not None and prev.get("time") != bar.get("time") else None,
                   tempo_marked=tempo, rehearsal=bar.get("rehearsal"), free_region=region, entering_region=entering,
                   a_tempo=a_tempo and tempo is not None, total_bars=doc["total_bars"])
        events = bar["events"] or [{"kind": "bar-rest", "bars": 1}]
        if len(events) == 1 and events[0]["kind"] == "bar-rest":
            run = 1
            while b + run < len(bars) and _is_rest_bar(bars[b + run]):
                run += 1
            ev = {"kind": "bar-rest", "bars": run}
            out.append((L.bar_heading(bar["number"], bar["number"] + run - 1 if run > 1 else None),
                        [announce(ap, abar, ev, ctx, s, by_bar=True)]))
            ctx = Context(ap.name, bar["number"], s.pitch_mode)
            b += run
            continue
        lines = []
        first = True
        for ev in events:
            if _is_tie_continuation(ev):
                continue
            lines.append(announce(ap, abar if first else replace(abar, entering_region=False, a_tempo=False,
                                                                     key_changed=False, time_changed=None,
                                                                     tempo_marked=None, rehearsal=None),
                                  ev, ctx, s, by_bar=first))
            ctx = Context(ap.name, bar["number"], s.pitch_mode)
            first = False
        if not lines:  # only tie continuations: the note from an earlier bar is still sounding
            cont = events[0]
            held = {"kind": "held", "pos": cont.get("pos"), "written": cont.get("written"), "concert": cont.get("concert"),
                    "held_from": cont.get("held_from")}
            lines.append(announce(ap, abar, held, ctx, s, by_bar=True))
            ctx = Context(ap.name, bar["number"], s.pitch_mode)
        out.append((L.bar_heading(bar["number"]), lines))
        b += 1
    return out


def _parts(doc: dict, parts: list[int] | None) -> list[int]:
    return list(range(len(doc["parts"]))) if parts is None else parts


def _part_title(doc: dict, i: int, s: Settings) -> str:
    p = doc["parts"][i]
    return (p.get("name_nb") or p["name"]) if s.nb else p["name"]


def to_html(doc: dict, s: Settings = Settings(), parts: list[int] | None = None) -> str:
    e = html.escape
    lang = "nb" if s.nb else "en"
    out = [f'<!DOCTYPE html>\n<html lang="{lang}">\n<head><meta charset="utf-8"><title>{e(doc["title"])}</title></head>\n'
           f'<body>\n<h1>{e(doc["title"])}</h1>\n']
    for i in _parts(doc, parts):
        out.append(f"<h2>{e(_part_title(doc, i, s))}</h2>\n")
        for heading, lines in part_lines(doc, i, s):
            out.append(f"<h3>{e(heading)}</h3>\n<ul>\n" + "".join(f"<li>{e(x)}</li>\n" for x in lines) + "</ul>\n")
    out.append("</body>\n</html>\n")
    return "".join(out)


def to_text(doc: dict, s: Settings = Settings(), parts: list[int] | None = None) -> str:
    out = [doc["title"], "\n\n"]
    for i in _parts(doc, parts):
        t = _part_title(doc, i, s)
        out += [t, "\n", "=" * len(t), "\n\n"]
        for heading, lines in part_lines(doc, i, s):
            out += [heading, "\n"] + [f"  {x}\n" for x in lines] + ["\n"]
    return "".join(out)


def load_composition(path: Path | None) -> dict | None:
    return json.loads(Path(path).read_text()) if path and Path(path).exists() else None
