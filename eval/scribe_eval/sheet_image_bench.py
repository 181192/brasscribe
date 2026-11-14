"""Benchmark for reading printed music from a picture: pages rendered here, read back, scored on their notes.

The pages are engraved by MuseScore from scores written in this file, so every note on them is known:
*Old Hundredth* (Louis Bourgeois, 1551, public domain) as one line and as a hymn on two staves, and
invented pieces: a march, a waltz in the bass clef, a jig in 6/8, four parts in score, a line long
enough to need a second page, a guitar line with a tab staff under it, and a tune that starts on a pickup
and changes key and time twice. Each page is kept twice:

  screenshot  the page as a notation program shows it, at the width of a phone's screen
  photo       the same page as a phone would photograph it on a stand, and at a lower resolution than
              the screenshot: turned a few degrees, seen at an angle, lit from one side with a shadow
              across it, out of focus, noisy, saved as a JPEG

A recogniser reads each set to MusicXML, and what it read is compared with what was written, staff by
staff in score order (written pitches: a recogniser cannot know a part's transposition):

  pitch_f1      notes found at the right pitch, in order (precision and recall over all notes)
  note_f1       the same with the note's length right too
  bars_ok       bars that are right in every note: pitch, place in the bar and length
  bars_found    bars read, against bars written (1.0 when the count is the same)
  pages_failed  pieces the recogniser gave nothing for (they score as nothing found)
  doubt_found   of the bars read wrong, the share the engine marks as in doubt (scribe_engine.sheet.doubtful_bars:
                a bar that does not add up to its time signature); 1.0 when no bar is wrong
  doubt_false   bars read right that it marks all the same (a count)

    python -m scribe_eval.sheet_image_bench build [--data DIR]                       the pages (MuseScore)
    python -m scribe_eval.sheet_image_bench prepare [--data DIR] [--recogniser N]    read them (the adapter N)
    python -m scribe_eval.sheet_image_bench report [--data DIR] [--recogniser N]     per-piece scores
    python -m scribe_eval.sheet_image_bench freeze [--data DIR]                      copy what was read to eval/fixtures

Engraved pages, one engraver, one house style: a recogniser that does well here still has to be tried
on real photographs. What the set does show is whether the notes come through at all.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import time
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path

from scribe_music import written

SET = "sheet-image"
SETS = ("screenshot", "photo")
RECOGNISER = "homr"  # the adapter the engine reads pictures with
REFERENCE = "reference.musicxml"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / SET
SCREENSHOT_DPI = 130  # an A4 page 1075 pixels wide: a phone's screenshot
PHOTO_DPI = 200  # what the photo is made from
PHOTO_WIDTH = 1000  # pixels across the photo, desk and all: the page in it is narrower than the screenshot's
DIVISIONS = 4  # per quarter: a sixteenth is 1
TYPES = {16: ("whole", 0), 12: ("half", 1), 8: ("half", 0), 6: ("quarter", 1), 4: ("quarter", 0), 3: ("eighth", 1),
         2: ("eighth", 0), 1: ("16th", 0)}
LETTERS = "CDEFGAB"
SEMITONES = (0, 2, 4, 5, 7, 9, 11)
SHARPS = "FCGDAEB"  # the order sharps enter a key signature; flats enter in reverse


# ---------------------------------------------------------------- the pieces

class _Dice:
    """A small generator of its own, so the invented pieces are the same on every Python."""

    def __init__(self, seed: int):
        self.state = seed

    def below(self, n: int) -> int:
        self.state = (self.state * 1103515245 + 12345) % 2 ** 31
        return (self.state >> 8) % n

    def pick(self, items):
        return items[self.below(len(items))]


def _key_alter(letter: str, fifths: int) -> int:
    if fifths > 0:
        return 1 if letter in SHARPS[:fifths] else 0
    return -1 if letter in SHARPS[::-1][:-fifths] else 0


def _note(degree: int, fifths: int, chromatic: int = 0) -> tuple[str, int, int]:
    """A staff position (octave * 7 + letter index) as (letter, alter, octave) in the key."""
    letter = LETTERS[degree % 7]
    return letter, _key_alter(letter, fifths) + chromatic, degree // 7


def midi(note: tuple[str, int, int]) -> int:
    letter, alter, octave = note
    return 12 * (octave + 1) + SEMITONES[LETTERS.index(letter)] + alter


# Bars of rhythm per meter, in sixteenths.
RHYTHMS = {
    (4, 4): [(4, 4, 4, 4), (8, 4, 4), (4, 2, 2, 4, 4), (6, 2, 4, 4), (2, 2, 2, 2, 8), (4, 4, 8), (12, 4), (16,), (2, 2, 4, 2, 2, 4)],
    (2, 4): [(4, 4), (2, 2, 4), (3, 1, 4), (2, 2, 2, 2), (1, 1, 1, 1, 4), (4, 2, 2), (8,), (3, 1, 2, 2), (2, 1, 1, 4)],
    (3, 4): [(4, 4, 4), (8, 4), (4, 2, 2, 4), (12,), (6, 2, 4), (2, 2, 2, 2, 4), (4, 8)],
    (6, 8): [(2, 2, 2, 2, 2, 2), (4, 2, 4, 2), (6, 6), (4, 2, 2, 2, 2), (6, 4, 2), (2, 2, 2, 6), (12,)],
}


def line(seed: int, bars: int, meter: tuple[int, int], fifths: int, low: int, high: int, busy: bool = True) -> list[list[tuple]]:
    """An invented line: `bars` bars of (staff positions or None for a rest, sixteenths, chromatic alteration,
    tied to the next). It moves by step and small leaps between the staff positions `low` and `high`."""
    dice = _Dice(seed)
    rhythms = RHYTHMS[meter] if busy else [r for r in RHYTHMS[meter] if min(r) >= 2]
    at = (low + high) // 2
    out = []
    for bar in range(bars):
        last = bar == bars - 1
        rhythm = (sum(RHYTHMS[meter][0]),) if last else dice.pick(rhythms)
        events = []
        for i, length in enumerate(rhythm):
            if not last and length >= 4 and dice.below(9) == 0:
                events.append((None, length, 0, False))
                continue
            at = min(high, max(low, at + dice.pick((-2, -1, -1, 1, 1, 2, 0, 3, -3))))
            chromatic = dice.pick((1, -1)) if dice.below(14) == 0 and not last else 0
            if chromatic:  # never a double sharp or flat: a note the key alters is made natural instead
                chromatic = -_key_alter(LETTERS[at % 7], fifths) or chromatic
            events.append(((at,), length, chromatic, False))
        # A tie over the bar line now and then: the next bar starts on the same note.
        if not last and events[-1][0] and not events[-1][2] and dice.below(8) == 0:
            events[-1] = (*events[-1][:3], True)
        if out and out[-1][-1][3] and events[0][0]:
            events[0] = (out[-1][-1][0], events[0][1], 0, events[0][3])
        elif out and out[-1][-1][3]:
            out[-1][-1] = (*out[-1][-1][:3], False)
        out.append(events)
    return out


# Old Hundredth: the tune, and the chord under each note (apps/fixtures/make-old-hundredth.py has the same).
HUNDREDTH = [("G4 G4 F#4 E4 D4 G4 A4 B4", "G G D C G C D G"), ("B4 B4 B4 A4 G4 C5 B4 A4", "G Em G D Em C G D"),
             ("G4 A4 B4 A4 G4 E4 F#4 G4", "G D G D C Am D G"), ("D5 B4 G4 A4 C5 B4 A4 G4", "G Em C D Am G D G")]
HUNDREDTH_RHYTHM = (8, 4, 4, 4, 4, 4, 4, 8)  # then a half rest: three bars of 4/4 to the line
CHORDS = {"G": "GBD", "C": "CEG", "D": "DFA", "Em": "EGB", "Am": "ACE"}


def _position(name: str) -> int:
    return int(name[-1]) * 7 + LETTERS.index(name[0])


def _below(top: int, letters: str, skip: int = 0) -> int:
    """The nearest staff position under `top` on one of `letters`, skipping `skip` of them."""
    at = top - 1
    while True:
        if LETTERS[at % 7] in letters:
            if skip == 0:
                return at
            skip -= 1
        at -= 1


def hundredth(voices: str) -> list[list[tuple]]:
    """Old Hundredth's twelve bars: "tune", "upper" (the tune over an alto) or "lower" (tenor over the bass)."""
    events = []
    for tune, chords in HUNDREDTH:
        for name, chord, length in zip(tune.split(), chords.split(), HUNDREDTH_RHYTHM):
            top = _position(name)
            alto = _below(top, CHORDS[chord])
            if voices == "tune":
                positions = (top,)
            elif voices == "upper":
                positions = (alto, top)
            else:
                tenor = _below(alto, CHORDS[chord])
                bass = _below(min(tenor, 3 * 7 + 4), CHORDS[chord][0])
                positions = (bass, tenor)
            events.append((positions, length, 0, False))
        events.append((None, 8, 0, False))
    bars, bar, filled = [], [], 0
    for e in events:
        bar.append(e)
        filled += e[1]
        if filled == 16:
            bars.append(bar)
            bar, filled = [], 0
    return bars


GUITAR = (64, 59, 55, 50, 45, 40)  # the open strings, highest first


def _fret(pitch: int) -> tuple[int, int]:
    """(string, fret) for a pitch in the first position: the lowest string that reaches it within four frets."""
    for string, open_pitch in reversed(list(enumerate(GUITAR, 1))):
        if 0 <= pitch - open_pitch <= 4:
            return string, pitch - open_pitch
    return 1, pitch - GUITAR[0]


def changing() -> tuple[list[list[tuple]], dict[int, tuple[int, int, int]]]:
    """A tune that starts on a pickup of one quarter note and changes key and time twice: its bars, and the bar
    (from 0) each change is at, with the meter and key from there."""
    sections = [((4, 4), 1, 8, 67), ((3, 4), -3, 8, 71), ((6, 8), 2, 8, 73)]
    bars: list[list[tuple]] = [[((32,), 4, 0, False)]]
    changes = {}
    for meter, fifths, count, seed in sections:
        changes[len(bars)] = (*meter, fifths)
        bars += line(seed, count, meter, fifths, 30, 38, busy=False)
    return bars, changes


# name -> (title, meter, key, [(part name, clef, bars, tab staff under it)], and for a piece that has them: the
#          changes of meter and key, by the bar they are at)
def pieces() -> dict[str, tuple]:
    treble, bass = ("G", 2, 0), ("F", 4, 0)
    tune, changes = changing()
    return {
        "pickup-and-changes": ("A tune that changes", (4, 4), 1, [("Cornet", treble, tune, False)], changes),
        "old-hundredth-tune": ("Old Hundredth", (4, 4), 1, [("Cornet", treble, hundredth("tune"), False)]),
        "old-hundredth-hymn": ("Old Hundredth", (4, 4), 1, [("Organ", (treble, bass), (hundredth("upper"), hundredth("lower")), False)]),
        "march": ("A march", (2, 4), -2, [("Cornet", treble, line(11, 32, (2, 4), -2, 30, 39), False)]),
        "waltz-bass-clef": ("A waltz", (3, 4), -1, [("Euphonium", bass, line(23, 32, (3, 4), -1, 17, 27, busy=False), False)]),
        "jig": ("A jig", (6, 8), -3, [("Horn", treble, line(37, 24, (6, 8), -3, 29, 38), False)]),
        "four-parts": ("Four parts", (4, 4), 2, [
            ("Cornet 1", treble, line(41, 16, (4, 4), 2, 32, 40, busy=False), False),
            ("Cornet 2", treble, line(43, 16, (4, 4), 2, 29, 36, busy=False), False),
            ("Horn", treble, line(47, 16, (4, 4), 2, 28, 34, busy=False), False),
            ("Euphonium", bass, line(53, 16, (4, 4), 2, 17, 26, busy=False), False)]),
        "two-pages": ("A long line", (4, 4), 3, [("Cornet", treble, line(59, 96, (4, 4), 3, 29, 39), False)]),
        "guitar-with-tab": ("A guitar line", (4, 4), 0, [("Guitar", ("G", 2, -1), line(61, 16, (4, 4), 0, 23, 32, busy=False), True)]),
    }


# ---------------------------------------------------------------- MusicXML of a piece

def _note_xml(note: tuple[str, int, int] | None, length: int, chord: bool, staff: int | None, ties: tuple[bool, bool],
              shown_octave: int = 0, tab: bool = False) -> str:
    kind, dots = TYPES[length]
    x = ["<note>"]
    if chord:
        x.append("<chord/>")
    if note is None:
        x.append("<rest/>")
    else:
        letter, alter, octave = note
        x.append(f"<pitch><step>{letter}</step>" + (f"<alter>{alter}</alter>" if alter else "") + f"<octave>{octave + shown_octave}</octave></pitch>")
    x.append(f"<duration>{length}</duration>")
    x += [f'<tie type="{t}"/>' for t, on in zip(("stop", "start"), ties) if on]
    x.append(f"<voice>{5 if tab else 1}</voice><type>{kind}</type>" + "<dot/>" * dots)
    if tab:
        x.append("<stem>none</stem>")
    if staff:
        x.append(f"<staff>{staff}</staff>")
    marks = "".join(f'<tied type="{t}"/>' for t, on in zip(("stop", "start"), ties) if on)
    if tab and note is not None:
        string, fret = _fret(midi(note) + 12 * shown_octave)
        marks += f"<technical><string>{string}</string><fret>{fret}</fret></technical>"
    if marks:
        x.append(f"<notations>{marks}</notations>")
    return "".join(x) + "</note>"


def _clef_xml(clef: tuple[str, int, int], number: int | None) -> str:
    sign, at, octave = clef
    n = f' number="{number}"' if number else ""
    return f"<clef{n}><sign>{sign}</sign><line>{at}</line>" + (f"<clef-octave-change>{octave}</clef-octave-change>" if octave else "") + "</clef>"


def musicxml(name: str) -> str:
    """The piece as MusicXML: what MuseScore engraves, and the reference the reading is scored against."""
    title, (beats, unit), fifths, parts, *more = pieces()[name]
    changes = more[0] if more else {}
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<score-partwise version="4.0">', f"<work><work-title>{title}</work-title></work>",
           "<part-list>"]
    out += [f'<score-part id="P{i}"><part-name>{part[0]}</part-name></score-part>' for i, part in enumerate(parts, 1)]
    out.append("</part-list>")
    for i, (_, clef, bars, tab) in enumerate(parts, 1):
        staves = list(zip(clef, bars)) if isinstance(clef[0], tuple) else [(clef, bars)]
        many = len(staves) > 1 or tab
        out.append(f'<part id="P{i}">')
        pickup = bool(changes) and sum(e[1] for e in staves[0][1][0]) < beats * 16 // unit
        for b in range(len(staves[0][1])):
            # A pickup is bar 0 and outside the count, as notation programs write it.
            out.append(f'<measure number="{b + 1 - pickup}"' + (' implicit="yes">' if pickup and b == 0 else ">"))
            if b in changes and b > 0:
                beats, unit, fifths = changes[b]
                out.append(f"<attributes><key><fifths>{fifths}</fifths></key>"
                           f"<time><beats>{beats}</beats><beat-type>{unit}</beat-type></time></attributes>")
            if b == 0:
                out.append(f"<attributes><divisions>{DIVISIONS}</divisions><key><fifths>{fifths}</fifths></key>"
                           f"<time><beats>{beats}</beats><beat-type>{unit}</beat-type></time>")
                if many:
                    out.append(f"<staves>{len(staves) + tab}</staves>")
                out += [_clef_xml(c, s if many else None) for s, (c, _) in enumerate(staves, 1)]
                if tab:
                    out.append('<clef number="2"><sign>TAB</sign><line>5</line></clef><staff-details number="2"><staff-lines>6</staff-lines>')
                    for at, pitch in enumerate(reversed(GUITAR), 1):
                        out.append(f'<staff-tuning line="{at}"><tuning-step>{LETTERS[(SEMITONES.index(pitch % 12))]}</tuning-step>'
                                   f"<tuning-octave>{pitch // 12 - 1}</tuning-octave></staff-tuning>")
                    out.append("</staff-details>")
                out.append("</attributes>")
            for s, (c, staff_bars) in enumerate(staves, 1):
                for as_tab in ((False, True) if tab else (False,)):
                    if s > 1 or as_tab:
                        out.append(f"<backup><duration>{sum(e[1] for e in staff_bars[b])}</duration></backup>")
                    for k, (positions, length, chromatic, tie) in enumerate(staff_bars[b]):
                        previous = staff_bars[b][k - 1] if k else (staff_bars[b - 1][-1] if b else None)
                        tied_in = bool(previous and previous[3])
                        for j, position in enumerate(positions or (None,)):
                            note = None if position is None else _note(position, fifths, chromatic)
                            out.append(_note_xml(note, length, j > 0, (2 if as_tab else s) if many else None, (tied_in, tie),
                                                 0, as_tab))
            out.append("</measure>")
        out.append("</part>")
    out.append("</score-partwise>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the pages

def _pages(folder: Path, kind: str) -> list[Path]:
    return sorted(folder.glob(f"{kind}-*.png")) + sorted(folder.glob(f"{kind}-*.jpg"))


def _engrave(xml: Path, stem: Path, dpi: int) -> list[Path]:
    """MuseScore's pages of `xml` as <stem>-<n>.png on white paper."""
    from PIL import Image

    mscore = shutil.which("mscore")
    if not mscore:
        raise SystemExit("the pages are engraved by MuseScore: mscore is not on PATH")
    subprocess.run([mscore, "-r", str(dpi), "-o", str(stem.with_suffix(".png")), str(xml)], capture_output=True, timeout=300)
    pages = sorted(stem.parent.glob(f"{stem.name}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
    if not pages:
        raise SystemExit(f"MuseScore wrote no page for {xml}")
    for p in pages:  # MuseScore's PNG is transparent where the paper is
        im = Image.open(p).convert("RGBA")
        paper = Image.new("RGBA", im.size, "white")
        paper.alpha_composite(im)
        paper.convert("L").save(p, optimize=True)
    return pages


def photograph(page: Path, out: Path, seed: int) -> None:
    """`page` as a phone's photo of it on a stand: on a desk's grey, turned up to three degrees, seen at an angle
    from below and from one side, lit from one corner with the shadow of the hand across it, out of focus, with
    the sensor's noise, PHOTO_WIDTH pixels across, saved as a JPEG of low quality."""
    import numpy as np
    from PIL import Image, ImageFilter

    dice = _Dice(seed)
    im = Image.open(page).convert("L")
    w, h = im.size
    desk = Image.new("L", (int(w * 1.10), int(h * 1.07)), 96)
    desk.paste(im, ((desk.width - w) // 2, (desk.height - h) // 2))
    angle = (dice.below(600) - 300) / 100  # up to three degrees either way
    desk = desk.rotate(angle, resample=Image.BICUBIC, fillcolor=96)
    W, H = desk.size
    lean = 0.06 + dice.below(40) / 1000  # the far edge of the page is narrower
    skew = (dice.below(60) - 30) / 1000  # and one side is further away than the other
    corners = (lean * W, skew * H if skew > 0 else 0, 0, H, W, H, (1 - lean) * W, -skew * H if skew < 0 else 0)
    desk = desk.transform((W, H), Image.QUAD, corners, resample=Image.BICUBIC, fillcolor=96)
    desk = desk.resize((PHOTO_WIDTH, round(PHOTO_WIDTH * H / W)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.1))
    a = np.asarray(desk, dtype=np.float32)
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    light = 0.52 + 0.48 * (xs / a.shape[1] * 0.6 + ys / a.shape[0] * 0.4)  # half as bright in the far corner
    edge = (0.25 + dice.below(50) / 100) * a.shape[0]  # the shadow of the hand that holds the phone
    light = light * (1 - 0.35 / (1 + np.exp((ys - edge - 0.15 * xs) / 25)))
    rng = np.random.default_rng(seed)
    a = a * light + rng.normal(0, 6.0, a.shape)
    paper = np.stack([a * 1.0, a * 0.97, a * 0.90], axis=-1)  # warm light on white paper
    Image.fromarray(np.clip(paper, 0, 255).astype(np.uint8), "RGB").save(out, quality=55)


def engraver() -> str:
    """The MuseScore that engraves the pages, as it names itself: the pages are its, and another version's may
    differ."""
    mscore = shutil.which("mscore")
    if not mscore:
        return "none"
    said = subprocess.run([mscore, "--version"], capture_output=True, text=True, timeout=120)
    return (said.stdout or said.stderr).strip().splitlines()[-1] if (said.stdout or said.stderr).strip() else "unknown"


def build(data: Path, only: tuple[str, ...] = ()) -> list[Path]:
    made = []
    for seed, name in enumerate(pieces(), 1):
        if only and name not in only:
            continue
        dest = Path(data) / "eval" / SET / name
        dest.mkdir(parents=True, exist_ok=True)
        for old in [*_pages(dest, "screenshot"), *_pages(dest, "photo")]:
            old.unlink()
        (dest / REFERENCE).write_text(musicxml(name))
        (dest / "engraver.txt").write_text(engraver() + "\n")
        _engrave(dest / REFERENCE, dest / "screenshot", SCREENSHOT_DPI)
        with tempfile.TemporaryDirectory() as tmp:
            for n, page in enumerate(_engrave(dest / REFERENCE, Path(tmp) / "page", PHOTO_DPI), 1):
                photograph(page, dest / f"photo-{n}.jpg", seed * 100 + n)
        made.append(dest)
    return made


def entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / SET
    return sorted(p for p in root.iterdir() if (p / REFERENCE).exists()) if root.is_dir() else []


def read_file(kind: str, recogniser: str = RECOGNISER) -> str:
    """The file a recogniser's reading of one set of pages is kept in, next to the reference."""
    return f"{kind}.{recogniser}.musicxml"


def prepare(entry: Path, recogniser: str = RECOGNISER, again: bool = False) -> dict[str, float]:
    """Read both sets of pages of `entry` with the adapter `recogniser`. A reading that fails leaves no file.
    Returns the seconds each set took."""
    from .paths import ADAPTERS

    took = {}
    for kind in SETS:
        out = entry / read_file(kind, recogniser)
        if out.exists() and not again:
            continue
        out.unlink(missing_ok=True)
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmp:  # the set's pages alone in a folder, in order
            for page in _pages(entry, kind):
                shutil.copyfile(page, Path(tmp) / page.name)
            subprocess.run([str(ADAPTERS / recogniser / "run.sh"), tmp, str(out)], check=False)
        took[kind] = time.time() - t0
    return took


# ---------------------------------------------------------------- the score

def _tokens(staff: written.Staff, lengths: bool) -> list[tuple]:
    shown = 12 * staff.clef_octave
    return [(n.pitch - shown, n.dur) if lengths else (n.pitch - shown,) for bar in staff.bars for n in bar.notes]


def _bar_tokens(staff: written.Staff) -> list[tuple]:
    shown = 12 * staff.clef_octave
    return [tuple((n.start, n.pitch - shown, n.dur) for n in bar.notes) for bar in staff.bars]


def _same(a: list, b: list) -> int:
    """How many items of `a` are found in `b` in the same order (the longest matching blocks)."""
    return sum(block.size for block in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


def _f1(hit: int, wanted: int, given: int) -> float:
    return 2 * hit / (wanted + given) if wanted + given else 1.0


def compare(reference: written.WrittenScore, read: written.WrittenScore | None) -> dict[str, float]:
    """Counts for one piece: staves are paired in score order, tab staves left out on both sides (a tab staff
    says the same notes again). A staff that was not read counts as all its notes missed."""
    ref = [s for s in reference.staves if not s.is_tab]
    got = [s for s in read.staves if not s.is_tab and s.bars] if read else []
    from scribe_engine.sheet import doubtful_bars

    c = dict.fromkeys(("notes", "read", "pitch", "note", "bars", "bars_read", "bars_ok", "wrong", "wrong_marked", "right_marked"), 0)
    for i in range(max(len(ref), len(got))):
        r = ref[i] if i < len(ref) else written.Staff("", 0, "G", 0)
        g = got[i] if i < len(got) else written.Staff("", 0, "G", 0)
        c["notes"] += r.notes()
        c["read"] += g.notes()
        c["pitch"] += _same(_tokens(r, False), _tokens(g, False))
        c["note"] += _same(_tokens(r, True), _tokens(g, True))
        if i < len(ref):
            c["bars"] += len(r.bars)
            c["bars_read"] += len(g.bars)
            c["bars_ok"] += _same(_bar_tokens(r), _bar_tokens(g))
            if len(r.bars) == len(g.bars):  # bar for bar only where the bars can be told apart
                marked = set(doubtful_bars(g))
                for k, (want, got_bar) in enumerate(zip(_bar_tokens(r), _bar_tokens(g))):
                    c["wrong"] += want != got_bar
                    c["wrong_marked"] += want != got_bar and k in marked
                    c["right_marked"] += want == got_bar and k in marked
    return c


def metrics(c: dict[str, float]) -> dict[str, float]:
    return {"pitch_f1": _f1(c["pitch"], c["notes"], c["read"]), "note_f1": _f1(c["note"], c["notes"], c["read"]),
            "bars_ok": c["bars_ok"] / c["bars"] if c["bars"] else 1.0,
            "bars_found": min(c["bars"], c["bars_read"]) / max(c["bars"], c["bars_read"]) if c["bars"] else 1.0,
            "doubt_found": c["wrong_marked"] / c["wrong"] if c["wrong"] else 1.0, "doubt_false": float(c["right_marked"])}


def evaluate(data: Path, recogniser: str = RECOGNISER, root: Path | None = None) -> tuple[dict[str, float], list[dict]]:
    """The suite's metrics (<set>.<metric>, over all notes and bars of the set) and a row per piece and set.
    The pieces are the ones under `root` (the data folder's set by default)."""
    folders = sorted(p for p in root.iterdir() if (p / REFERENCE).exists()) if root else entries(data)
    out: dict[str, float] = {}
    rows = []
    for kind in SETS:
        total: dict[str, float] = {}
        failed = 0
        for entry in folders:
            reference = written.read(entry / REFERENCE)
            path = entry / read_file(kind, recogniser)
            try:
                read = written.read(path) if path.exists() else None
            except ValueError:
                read = None
            failed += read is None
            c = compare(reference, read)
            rows.append({"piece": entry.name, "set": kind, "read": read is not None, **c, **metrics(c)})
            for k, v in c.items():
                total[k] = total.get(k, 0) + v
        if folders:
            out.update({f"{kind}.{k}": v for k, v in metrics(total).items()})
            out[f"{kind}.pages_failed"] = float(failed)
    out["pieces"] = float(len(folders))
    return out, rows


def freeze(data: Path, recogniser: str = RECOGNISER) -> int:
    """Copy the references and what the recogniser read into eval/fixtures, where CI scores them."""
    n = 0
    for entry in entries(data):
        dest = FIXTURES / entry.name
        dest.mkdir(parents=True, exist_ok=True)
        for name in (REFERENCE, "engraver.txt", *(read_file(kind, recogniser) for kind in SETS)):
            if (entry / name).exists():
                shutil.copy2(entry / name, dest / name)
                n += 1
    return n


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "prepare", "report", "freeze"])
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--recogniser", default=RECOGNISER, help="the adapter that reads the pages (ml/adapters/<name>)")
    ap.add_argument("--again", action="store_true", help="prepare: read pages that were read before too")
    args = ap.parse_args()
    if args.command == "build":
        for d in build(args.data):
            print(d.name, len(_pages(d, "screenshot")), "page(s)", flush=True)
    elif args.command == "prepare":
        for d in entries(args.data):
            took = prepare(d, args.recogniser, args.again)
            print(d.name, " ".join(f"{k} {v:.0f}s" for k, v in took.items()) or "read before", flush=True)
    elif args.command == "freeze":
        print(freeze(args.data, args.recogniser), "files in", FIXTURES)
    else:
        summary, rows = evaluate(args.data, args.recogniser)
        for r in rows:
            state = "" if r["read"] else "  NOT READ"
            print(f"{r['piece']:20s} {r['set']:10s} pitch {r['pitch_f1']:.3f}  note {r['note_f1']:.3f}  bars ok {r['bars_ok']:.3f}  "
                  f"bars {r['bars_read']}/{r['bars']}  notes {r['read']}/{r['notes']}{state}")
        print(" ".join(f"{k}={v:.3f}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
