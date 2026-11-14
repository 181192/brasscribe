"""Printed music from a picture: a screenshot, a photo of a page or a PDF read into a score or a tab.

The other profiles listen to a recording. These two read pages: one picture, one PDF, or several pages in
order (stored as one archive, pages.py), through the homr adapter, which writes what it reads as MusicXML.

  sheet      the band's target: the page as a score. What was read is kept as it was written (parts, clefs,
             keys, bars), given the job's title, and exported like any band score: PDF, MIDI, MP3, the
             parts, braille and the talking score. Nothing is arranged: a lead sheet stays a lead sheet.
  sheet-tab  the fretted target: the notes of the first staff as tab for one instrument, through the same
             fingering as a recording's (tab.py, bass_tab.py). A guitar's and a bass's notation is written
             an octave above where it sounds, so with octave auto the line is taken an octave down for
             them (and moved by octaves when it still lies outside the instrument); a tab staff on the
             page is not read.

  read     homr on the pages -> read.musicxml
  notes    (sheet-tab) the first staff's notes on a beat grid, as the tab profile's notes stage writes them
  arrange  sheet: the score, its parts and composition.json; sheet-tab: a string and a fret for every note
  export   as the target's other profiles

Doubt. The recogniser gives no confidence, so the one sign there is of a misreading is used: a bar whose
notes and rests do not add up to its time signature (the first and last bars aside: a pickup and its
complement), each staff counted by itself. Such a bar is marked "?" in the score and its notes get a confidence under the doubt
threshold, which the tab shows as its own "?". `scribe bench sheet-image` measures how many wrong bars the
rule finds and how many right ones it marks.

There is no recording, so the tempo is a fixed one (TEMPO_BPM): the times in composition.json and tab.json
are those of the score played at it.
"""

from __future__ import annotations

import json
import re
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from scribe_music import written

from . import bass_tab, pages, tab, targets
from . import stages as S
from .adapters import AdapterCancelled, AdapterError, environment_installed
from .dag import SOURCE, Input, Pipeline, Stage, StageContext, StageFailed

SCORE = "sheet"
TAB = "sheet-tab"
PROFILES = (SCORE, TAB)
THIS = Path(__file__).resolve()
RECOGNISER = "homr"
READ = "read.musicxml"
SUMMARY = "sheet.json"
TEMPO_BPM = 100  # quarter notes a minute: the page gives none that is read
NEIGHBOURS = 4  # bars to each side that say what a bar should hold when they agree against the time signature
DOUBTFUL = 0.3  # the confidence of a note in a bar that does not add up: under every profile's doubt threshold
TICKS = 24  # per quarter note (scribe_music.quantize.TICKS_PER_BEAT)
MAJOR_KEYS = ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#")
# Instruments whose notation is written an octave above where they sound.
OCTAVE_WRITTEN = (*bass_tab.INSTRUMENTS, "guitar-6", "guitar-7", "guitar-8")
# The lowest string of the lowest tuning offered and the top of the neck, for the instruments tab.HEARD has no range for.
BASS_RANGE = {"bass-4": (23, 67), "bass-5": (21, 67), "bass-6": (23, 72)}
# The sound a part plays with: the page does not say what the instrument is, and the recogniser calls every part a voice.
UNCERTAIN_COLOUR = "#0063A6"  # as the band scores' uncertain notes (scribe_music.musicxml, which loads music21)
SOUNDS = {"G": ("brass.cornet", 57), "F": ("brass.euphonium", 59), "C": ("brass.trombone", 58)}


# Why pages are not read, by the name the adapter gives it (run_adapter.py, REFUSAL): what the job's error says.
# The words are fixed: an app tells the cases apart by them, and nothing of the computer is in them.
NO_MUSIC = "no notes were found on the page"
REFUSALS = {
    "no_music": NO_MUSIC,
    "too_many_pages": f"there are more than {pages.MAX_PAGES} pages",
    "page_too_large": "a page is too large to read",
    "weights_missing": "the reader's files could not be fetched: check the network and try again",
    "no_space": "the computer's disk is full: free some space on it and try again",
}
NOT_READ = "the pages could not be read"
# What the API answers 503 with for a job of these profiles on a computer without the recogniser.
READER_MISSING = "reader_missing"
READER_MISSING_DETAIL = ("this computer has no reader of printed music installed: install it in Bandroom on that computer, "
                         "under Settings, Sheet music from pictures (an engine run from a checkout: "
                         "`uv sync --frozen --project ml/adapters/homr` on an Apple silicon Mac, `pixi install -e homr` "
                         "elsewhere)")
ONLY_TAB = "no staff of notes was found on the page: a tab staff is not read"


def is_sheet(profile: str) -> bool:
    """`profile` reads pages, not a recording."""
    return profile in PROFILES


def reader_installed(adapters_dir: Path) -> bool:
    """The recogniser's environment is on this computer. It is large and not every installation has it: without
    it the profiles here are not offered and a job of theirs is refused, where running the adapter would install
    it in the middle of the first job."""
    return environment_installed(adapters_dir, RECOGNISER)


# ---------------------------------------------------------------- options

def job_options(profile: str, params: dict) -> dict:
    """The options of a job that reads pages. The score takes none of the band's (nothing is arranged) or the
    tab's; the tab takes the tab profile's, except the two that describe a recording."""
    from .profiles import ARRANGEMENT_DEFAULTS

    if profile == TAB:
        if params.get("recording") is not None or params.get("chords") not in (None, "heard"):
            raise ValueError(f"recording, chords: the {TAB} profile reads a page, not a recording")
        opts = tab.options(params)
        opts.pop("recording", None)
        opts.pop("chords", None)
        return opts
    tab.refuse_options(profile, params)
    named = [k for k, default in ARRANGEMENT_DEFAULTS.items() if params.get(k) not in (None, default)]
    if named:
        raise ValueError(f"{', '.join(named)}: the {SCORE} profile writes the page as it is read; it is not arranged")
    return {}


# ---------------------------------------------------------------- read

def _without_paths(text: str) -> str:
    """`text` with every absolute path cut to its last name: what the recogniser says goes to the job's log, which
    a paired phone can read, and where things lie on the computer is not for it."""
    return re.sub(r"(?:[A-Za-z]:)?[/\\](?:[^\s/\\:'\"]+[/\\])+", "", text)


def _recognise(ctx: StageContext, source: Path, out: Path) -> None:
    """The recogniser on `source`. When it fails, what it said goes to the log without its paths, and the stage
    fails in fixed words: the reason the adapter named, or that the pages could not be read."""
    try:
        ctx.adapter(RECOGNISER, source, out)
    except AdapterCancelled:
        raise
    except AdapterError as e:
        said = str(e)
        for line in _without_paths(said).splitlines()[-12:]:
            ctx.log(line)
        named = re.findall(r"scribe-refusal: (\w+)", said)
        if named and named[-1] in REFUSALS:
            raise StageFailed(ctx.stage.name, REFUSALS[named[-1]]) from None
        if " failed (" not in said:  # stopped at its time limit, or from outside: the adapter registry's own words
            raise StageFailed(ctx.stage.name, said) from None
        raise StageFailed(ctx.stage.name, NOT_READ) from None


def read_stage(ctx: StageContext) -> None:
    """The pages through the recogniser. Several pages arrive as one archive and are read from a folder, which is
    in the stage's own folder so that it goes with the run."""
    source = ctx.inputs["pages"]
    out = ctx.out / READ
    if pages.is_archive(source):
        with tempfile.TemporaryDirectory(dir=ctx.out, prefix=".archive-") as tmp:
            try:
                count = pages.unpack(source, Path(tmp))
            except ValueError as e:
                raise StageFailed(ctx.stage.name, str(e)) from e
            ctx.log(f"{count} files")
            _recognise(ctx, Path(tmp), out)
    else:
        _recognise(ctx, source, out)
    try:
        score = written.read(out)
    except ValueError:
        raise StageFailed(ctx.stage.name, NOT_READ) from None
    if not sum(s.notes() for s in score.staves):
        raise StageFailed(ctx.stage.name, NO_MUSIC)
    ctx.log(f"{len(score.staves)} staves, {score.bars} bars, {sum(s.notes() for s in score.staves)} notes")


def _read() -> Stage:
    return Stage("read", "read", {"pages": Input(SOURCE)}, read_stage, adapter=RECOGNISER, code=(THIS, pages.THIS),
                 outputs=(READ,))


# ---------------------------------------------------------------- the grid

def bar_length(bar: written.Bar) -> Fraction | None:
    """What the bar's time signature says it holds, in quarter notes; None when the score gave none."""
    return Fraction(4 * bar.beats, bar.beat_unit) if bar.beats and bar.beat_unit else None


def doubtful_bars(staff: written.Staff) -> list[int]:
    """The bars of `staff` (from 0) whose notes and rests on that staff do not add up: each staff is counted by
    itself, so one staff's misread bar does not mark the staff beside it. The first and the last bar may be short
    (a pickup and the bar that completes it), and a bar the staff has nothing in is not one that does not add up.

    What a bar should add up to is what its time signature says, unless the bars around it agree on something
    else: when most of the bars within NEIGHBOURS of it (under the same signature) hold one amount that is not
    the signature's, the signature is what was misread, or a change of it was missed. Those bars are then held to
    what they agree on, and the first of them is in doubt in their place: it is where the signature is wrong."""
    bars = staff.bars
    last = len(bars) - 1
    expected: list[Fraction | None] = []
    for i, bar in enumerate(bars):
        nominal = bar_length(bar)
        around = [b.length for b in bars[max(0, i - NEIGHBOURS):i + NEIGHBOURS + 1]
                  if b.length and (b.beats, b.beat_unit) == (bar.beats, bar.beat_unit)]
        common = max(set(around), key=around.count) if around else nominal
        agreed = nominal is not None and len(around) >= 3 and around.count(common) * 2 > len(around)
        expected.append(common if agreed else nominal)
    out = []
    for i, bar in enumerate(bars):
        if expected[i] is None or not bar.length:
            continue
        elsewhere = expected[i] != bar_length(bar)  # the bars here agree against their signature
        starts = elsewhere and (i == 0 or expected[i - 1] != expected[i] or (bars[i - 1].beats, bars[i - 1].beat_unit) != (bar.beats, bar.beat_unit))
        if starts or (bar.length != expected[i] and not (i in (0, last) and bar.length < expected[i])):
            out.append(i)
    return out


def bar_starts(score: written.WrittenScore) -> list[Fraction]:
    """Where each bar starts, in quarter notes from the first full bar (a pickup starts before 0). A bar is as
    long as its time signature says, whatever was read in it, so that one misread bar does not move the rest;
    without a time signature it is as long as its longest staff."""
    lengths, pickup = [], Fraction(0)
    for i in range(score.bars):
        here = [s.bars[i] for s in score.staves if i < len(s.bars)]
        nominal = next((bar_length(b) for b in here if bar_length(b) is not None), None)
        held = max((b.length for b in here), default=Fraction(0))
        short = nominal is not None and i in (0, score.bars - 1) and 0 < held < nominal
        lengths.append(held if nominal is None or short else nominal)
        if short and i == 0 and score.bars > 1:
            pickup = held
    starts, at = [], -pickup
    for length in lengths:
        starts.append(at)
        at += length
    return starts


def sounding_notes(staff: written.Staff, starts: list[Fraction], doubt: set[int]) -> list[dict]:
    """The staff's notes as they sound (ties joined, the part's transposition applied): pitch, start and dur in
    ticks, the bar they start in, and a confidence that is DOUBTFUL in a bar of `doubt`."""
    out: list[dict] = []
    open_ties: dict[int, dict] = {}
    for i, bar in enumerate(staff.bars):
        for n in bar.notes:
            start = round((starts[i] + n.start) * TICKS)
            dur = max(1, round(n.dur * TICKS))
            pitch = n.pitch + staff.transpose
            held = open_ties.get(pitch)
            if n.tied_from_previous and held is not None and held["start"] + held["dur"] == start:
                held["dur"] += dur
                continue
            note = {"pitch": pitch, "start": start, "dur": dur, "bar": i, "confidence": DOUBTFUL if i in doubt else 1.0}
            out.append(note)
            open_ties[pitch] = note
    return sorted(out, key=lambda n: (n["start"], n["pitch"]))


def _seconds(tick: int) -> float:
    return round(tick / TICKS * 60 / TEMPO_BPM, 4)


def _beat_grid(first_tick: int, end_tick: int) -> tuple[list[float], int]:
    """(beat_times, first_downbeat) for a score played at TEMPO_BPM: a beat is a quarter note, tick 0 the first
    full bar's start, and a pickup lies on the beats before it."""
    before = -(first_tick // TICKS) if first_tick < 0 else 0  # whole beats that cover the pickup
    beats = before + end_tick // TICKS + 2
    return [round(i * 60 / TEMPO_BPM, 4) for i in range(beats)], before


def _timed(note: dict, before: int) -> dict:
    """`note` with the seconds it starts and ends at on the grid of _beat_grid."""
    return {**note, "onset_s": _seconds(note["start"] + before * TICKS), "offset_s": _seconds(note["start"] + note["dur"] + before * TICKS)}


# ---------------------------------------------------------------- the score (brass)

def _voice_id(staff: written.Staff, part: int, staves_in_part: int) -> str:
    return f"part-{part}" if staves_in_part == 1 else f"part-{part}-staff-{staff.number}"


def composition(score: written.WrittenScore, title: str):
    """The canonical score of what was read: a voice for every staff that has notes (a tab staff aside), at
    sounding pitch."""
    from scribe_music.score_model import Composition, KeySig, Meter, Note, ReviewItem, Voice, VoiceRole

    starts = bar_starts(score)
    staves = [s for s in score.staves if not s.is_tab]
    part_of, count, part = {}, {}, 0
    for s in score.staves:  # a part's staves are numbered from 1
        part += s.number == 1
        part_of[id(s)] = part
        count[part] = count.get(part, 0) + 1
    read = [(s, sounding_notes(s, starts, set(doubtful_bars(s)))) for s in staves]
    first = min((n["start"] for _, notes in read for n in notes), default=0)
    end = max((n["start"] + n["dur"] for _, notes in read for n in notes), default=0)
    beat_times, before = _beat_grid(first, end)
    voices, review = [], []
    for s, notes in read:
        if not notes:
            continue
        vid = _voice_id(s, part_of[id(s)], count[part_of[id(s)]])
        role = VoiceRole.MELODY if not voices else VoiceRole.HARMONY
        voices.append(Voice(vid, role, [Note(n["pitch"], n["start"], n["dur"], n["confidence"], ["page"], t["onset_s"], t["offset_s"])
                                        for n in notes for t in (_timed(n, before),)]))
        for bar in doubtful_bars(s):
            inside = [n for n in notes if n["bar"] == bar]
            if inside:
                at = round(starts[bar] * TICKS)
                review.append(ReviewItem(vid, at, max(max(n["start"] + n["dur"] for n in inside), at + 1), len(inside)))
    meters, keys = [], []
    lead = staves[0] if staves else None
    for i, bar in enumerate(lead.bars if lead else []):
        tick = max(0, round(starts[i] * TICKS))
        if bar.beats and bar.beat_unit and (not meters or (meters[-1].beats, meters[-1].beat_unit) != (bar.beats, bar.beat_unit)):
            meters.append(Meter(tick, bar.beats, bar.beat_unit))
        if bar.fifths is not None and (not keys or keys[-1].fifths != bar.fifths):
            keys.append(KeySig(tick, bar.fifths))
    return Composition(title, voices, meters or [Meter(0, 4, 4)], keys or [KeySig(0, 0)], beat_times, before, review=review)


def _direction(*children: ET.Element, staff: int | None = None) -> ET.Element:
    d = ET.Element("direction", {"placement": "above"})
    kind = ET.SubElement(d, "direction-type")
    kind.extend(children)
    if staff:
        ET.SubElement(d, "staff").text = str(staff)
    return d


def _first_note_index(measure: ET.Element) -> int:
    return next((i for i, el in enumerate(measure) if el.tag in ("note", "backup", "forward")), len(measure))


def _int(el: ET.Element | None, default: int = 0) -> int:
    try:
        return int(float(el.text)) if el is not None and el.text else default
    except ValueError:
        return default


def in_voices(measure: ET.Element, divisions: int) -> int:
    """Rewrite `measure` so that each staff's notes follow one another, a voice at a time, and return the
    divisions in force after it.

    The recogniser writes a system of two staves chord by chord, stepping back after each one. That is valid
    MusicXML, but a reader that follows one staff at a time (the talking score, a notation program's voices)
    loses its place in it. Here the notes are the recogniser's own elements, moved: within a staff, notes that
    start together and last as long are a chord, a note that starts while another still sounds goes to a second
    voice, and a gap is stepped over. What is not a note stays where it was, before or after the notes."""
    now = last = 0
    placed: list[tuple[int, int, int, ET.Element]] = []  # (staff, start, duration, note)
    before, after = [], []
    for el in list(measure):
        if el.tag == "attributes":
            divisions = _int(el.find("divisions"), divisions) or divisions
        if el.tag in ("backup", "forward"):
            now = max(0, now - _int(el.find("duration"))) if el.tag == "backup" else now + _int(el.find("duration"))
        elif el.tag == "note":
            dur = 0 if el.find("grace") is not None else _int(el.find("duration"))
            start = last if el.find("chord") is not None else now
            placed.append((_int(el.find("staff"), 1), start, dur, el))
            if el.find("chord") is None:
                last = now
                now += dur
        else:
            (after if placed else before).append(el)
        measure.remove(el)
    end = max((start + dur for _, start, dur, _ in placed), default=0)
    measure.extend(before)
    at = 0
    for staff in sorted({p[0] for p in placed}):
        voices: list[list[tuple[int, int, ET.Element]]] = []
        for _, start, dur, el in sorted((p for p in placed if p[0] == staff), key=lambda p: p[1]):  # stable: chords keep their order
            for voice in voices:
                tail_start, tail_dur, _ = voice[-1]
                if (tail_start, tail_dur) == (start, dur) or tail_start + tail_dur <= start:
                    voice.append((start, dur, el))
                    break
            else:
                voices.append([(start, dur, el)])
        for v, voice in enumerate(voices[:4], 1):  # a staff has four voices; a fifth is beyond what a page shows
            if at:
                ET.SubElement(ET.SubElement(measure, "backup"), "duration").text = str(at)
                at = 0
            previous = None
            for start, dur, el in voice:
                chord = previous is not None and previous == (start, dur)
                if not chord and start > at:
                    ET.SubElement(ET.SubElement(measure, "forward"), "duration").text = str(start - at)
                for old in el.findall("chord"):
                    el.remove(old)
                if chord:
                    el.insert(0, ET.Element("chord"))
                number = el.find("voice")
                if number is None:
                    number = ET.Element("voice")
                    el.insert(next((i + 1 for i, c in enumerate(el) if c.tag == "duration"), len(el)), number)
                number.text = str(4 * (staff - 1) + v)
                measure.append(el)
                if not chord:
                    at = start + dur
                previous = (start, dur)
    if at < end:
        ET.SubElement(ET.SubElement(measure, "forward"), "duration").text = str(end - at)
    measure.extend(after)
    return divisions


def written_score(read: Path, title: str, out: Path) -> written.WrittenScore:
    """The recogniser's MusicXML as the job's score, in `out`: its title is the job's, its parts are numbered
    (the recogniser names them all alike) and sound as brass, each staff's notes follow one another (in_voices), it
    plays at TEMPO_BPM, and every bar that does not
    add up is marked "?" over the staff, its notes in the colour of the band scores' uncertain notes."""
    score = written.read(read)
    root = ET.fromstring(read.read_bytes())
    for old in (*root.findall("work"), *root.findall("movement-title")):
        root.remove(old)
    work = ET.Element("work")
    ET.SubElement(work, "work-title").text = title
    root.insert(0, work)
    software = root.find("identification/encoding/software")
    if software is not None:
        software.text = f"scribe ({software.text})"
    doubt: dict[tuple[int, int], list[int]] = {}
    index = 0
    for p, part in enumerate(root.findall("part"), 1):
        staves = []
        while index < len(score.staves) and (not staves or score.staves[index].number > 1):
            staves.append(score.staves[index])
            index += 1
        info = next((sp for sp in root.iterfind("part-list/score-part") if sp.get("id") == part.get("id")), None)
        if info is not None:
            name = f"Part {p}"
            for tag in ("part-name", "score-instrument/instrument-name"):
                if info.find(tag) is not None:
                    info.find(tag).text = name
            for gone in info.findall("part-abbreviation"):
                info.remove(gone)
            if len(staves) == 1 and staves[0].clef in SOUNDS:
                sound, program = SOUNDS[staves[0].clef]
                if info.find("score-instrument/instrument-sound") is not None:
                    info.find("score-instrument/instrument-sound").text = sound
                if info.find("midi-instrument/midi-program") is not None:
                    info.find("midi-instrument/midi-program").text = str(program)
        measures = part.findall("measure")
        divisions = 1
        for measure in measures:
            divisions = in_voices(measure, divisions)
        if p == 1 and measures:
            measures[0].insert(_first_note_index(measures[0]), ET.Element("sound", {"tempo": str(TEMPO_BPM)}))
        for s in staves:
            for bar in doubtful_bars(s):
                if bar >= len(measures) or not s.bars[bar].notes:
                    continue
                doubt.setdefault((p, s.number), []).append(bar)
                mark = ET.Element("words")
                mark.text = "?"
                measures[bar].insert(_first_note_index(measures[bar]), _direction(mark, staff=s.number if len(staves) > 1 else None))
                for note in measures[bar].iter("note"):
                    if note.find("pitch") is not None and int(note.findtext("staff") or 1) == s.number:
                        note.set("color", UNCERTAIN_COLOUR)
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    (out / targets.BRASS.musicxml).write_text(head + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    return score


def summary(score: written.WrittenScore) -> dict:
    """What was read, for sheet.json: counts, and the bars in doubt per staff."""
    staves = [s for s in score.staves if not s.is_tab]
    return {"recogniser": RECOGNISER, "staves": len(staves), "bars": score.bars,
            "notes": sum(s.notes() for s in staves),
            "doubtful_bars": [{"staff": i, "bar": bar + 1} for i, s in enumerate(staves, 1) for bar in doubtful_bars(s) if s.bars[bar].notes]}


def score_stage(ctx: StageContext) -> None:
    from scribe_music.parts import split_parts

    title = ctx.params["title"]
    score = written_score(ctx.inputs["read"], title, ctx.out)
    split_parts(ctx.out / targets.BRASS.musicxml, ctx.out / "parts")
    composition(score, title).to_json(ctx.out / "composition.json")
    doc = summary(score)
    (ctx.out / SUMMARY).write_text(json.dumps(doc, indent=1))
    ctx.log(f"{doc['staves']} staves, {doc['bars']} bars, {doc['notes']} notes, {len(doc['doubtful_bars'])} bars in doubt")


def build_score(title: str, params: dict) -> Pipeline:
    from . import profiles as P

    band = targets.BRASS
    st = [_read(),
          Stage("arrange", "arrange", {"read": Input("read", READ)}, score_stage, params={"title": title},
                code=(THIS, S.MUSIC_SRC / "written.py", S.MUSIC_SRC / "parts.py"), outputs=("composition.json", band.musicxml, SUMMARY)),
          P._export("arrange", params.get("audio", True))]
    outputs = {k: v for k, v in P._outputs("arrange").items() if k != "separation-check.json"}
    outputs[SUMMARY] = ("arrange", SUMMARY)
    return Pipeline(SCORE, "sheet", st, outputs, {})


# ---------------------------------------------------------------- the tab (fretted)

def _range(instrument: str) -> tuple[int, int]:
    if instrument in BASS_RANGE:
        return BASS_RANGE[instrument]
    return tab.HEARD[instrument].lowest, tab.HEARD[instrument].highest


def octave_shift(pitches: list[int], instrument: str, clef_octave: int) -> int:
    """Semitones from what the staff shows to what the instrument plays, with octave auto: an octave down for an
    instrument written an octave high (unless the clef already said so and the recogniser read it), then by
    octaves towards the instrument's range while that leaves fewer notes outside it."""
    low, high = _range(instrument)

    def outside(shift: int) -> int:
        return sum(not low <= p + shift <= high for p in pitches)

    shift = -12 if instrument in OCTAVE_WRITTEN and clef_octave == 0 else 0
    for step in (12, -12):
        while outside(shift + step) < outside(shift):
            shift += step
    return shift


def tab_notes(score: written.WrittenScore, instrument: str, octave: str = "auto") -> dict:
    """The notes stage's document (as tab.played_notes writes it) for the first staff of `score` that has notes.

    A tab has no negative positions: a pickup is written as a full bar that starts with a rest."""
    staff = next((s for s in score.staves if not s.is_tab and s.notes()), None)
    if staff is None:
        raise ValueError(ONLY_TAB if any(s.is_tab for s in score.staves) else NO_MUSIC)
    starts = bar_starts(score)
    first_bar = next((b for b in staff.bars if bar_length(b)), None)
    if starts and starts[0] < 0 and first_bar is not None:  # the pickup's bar in full, its notes at its end
        starts = [s + bar_length(first_bar) for s in starts]
    notes = sounding_notes(staff, starts, set(doubtful_bars(staff)))
    shown = [n["pitch"] for n in notes]
    shift = octave_shift(shown, instrument, staff.clef_octave) if octave == "auto" else int(octave)
    beat_times, _ = _beat_grid(0, max(n["start"] + n["dur"] for n in notes))
    meter = next(((b.beats, b.beat_unit) for b in staff.bars if b.beats and b.beat_unit), (4, 4))
    fifths = next((b.fifths for b in staff.bars if b.fifths is not None), 0)
    return {"ticks_per_beat": TICKS,
            "notes": [{"pitch": n["pitch"] + shift, "start": n["start"], "dur": n["dur"], "confidence": n["confidence"],
                       "onset_s": _seconds(n["start"]), "offset_s": _seconds(n["start"] + n["dur"])} for n in notes],
            "octave_shift": shift, "octave_source": "auto" if octave == "auto" else "chosen", "octave_notes_moved": 0,
            "leftovers_dropped": 0, "meter": {"beats": meter[0], "beat_unit": meter[1]},
            "key": {"name": MAJOR_KEYS[max(-7, min(7, fifths)) + 7], "fifths": fifths, "mode": "major"},
            "tempo_bpm": float(TEMPO_BPM), "beat_times": beat_times, "first_downbeat": 0, "reference_pitch": None}


def notes_stage(ctx: StageContext) -> None:
    try:
        doc = tab_notes(written.read(ctx.inputs["read"]), ctx.params["instrument"], ctx.params.get("octave", "auto"))
    except ValueError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    doubtful = sum(n["confidence"] < bass_tab.DOUBT for n in doc["notes"])
    ctx.log(f"{len(doc['notes'])} notes, {doc['meter']['beats']}/{doc['meter']['beat_unit']}, {doc['key']['name']}; "
            f"octave {doc['octave_shift']:+d}, {doubtful} notes in doubt")
    (ctx.out / "tab-notes.json").write_text(json.dumps(doc, indent=1))


def build_tab(title: str, params: dict) -> Pipeline:
    opts = job_options(TAB, params)
    bass = opts["instrument"] in bass_tab.INSTRUMENTS
    read = {"instrument": opts["instrument"], **({"octave": opts["octave"]} if opts["octave"] != "auto" else {})}
    fingering = {"instrument": opts["instrument"], "tuning": opts["tuning"], "capo": opts["capo"], "style": opts["style"]}
    st = [_read(),
          Stage("notes", "notes", {"read": Input("read", READ)}, notes_stage, params=read,
                code=(THIS, S.MUSIC_SRC / "written.py"), outputs=("tab-notes.json",)),
          Stage("arrange", "arrange", {"notes": Input("notes", "tab-notes.json")},
                bass_tab.arrange_stage if bass else tab.arrange_stage,
                params={"title": title, "fingering": fingering, "layout": opts["layout"]},
                code=(tab.THIS, bass_tab.THIS, bass_tab.core_cli_path()), outputs=bass_tab.ARRANGED),
          Stage("export", "export", {"score": Input("arrange")}, bass_tab.export_stage,
                params={"musescore": bass_tab.musescore_fingerprint()}, code=(bass_tab.THIS,), outputs=("export.json",))]
    return Pipeline(TAB, "sheet", st, dict(bass_tab.OUTPUTS), opts)
