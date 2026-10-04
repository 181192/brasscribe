"""Ukulele, mandolin and rendered-guitar tab benchmark: the engine's tab profile on passages written here and rendered.

No recordings of a ukulele or a mandolin with their notes annotated were found (OpenMIC-2018 has clips
labelled as containing either, without notes). So the passages are written in this file and rendered
with FluidSynth and the MuseScore General SoundFont (MIT), which has sampled Ukulele and Mandolin
presets: one instrument each, one player-less performance, no room. That is weak evidence, and it is
all the evidence. The rules that read the notes were set on GuitarSet (guitar_tab_bench); the few that
were chosen while looking at passages of this file say so where they are defined (engine tab.py). Each
group has a `heldout` one, with other chords, scales and tempos and one more pattern (a melody high on the
top string over a ringing chord). They are reported, not tuned on, with three exceptions. The
threshold of the ukulele's overtone rule above the 12th fret was tried against them too, so they are not
a clean test of that rule. The rule that tells a chord heard again under that melody from a strum
struck again (engine tab.py, RING_*) was chosen on their chord-melody and strummed passages, the only ones
that have the pattern: those are scored apart (DEVELOPMENT), and a held-out group's numbers are from its
other passages. And which instruments the rule for overtones in a line that SwiftF0 did not hear applies to
(engine tab.py, Heard.unheard_overtones_out: a ukulele, not a mandolin or a guitar) was chosen while looking
at every held-out passage, the other passages included, so for that rule the split does not hold either.

The guitar groups are open chords picked and strummed, which GuitarSet's players do not play.

Each passage is rendered twice, alone (`instrument`) and under a bass and drums (`song`), and the
`song` mix is separated. Which of the separator's stems carries the instrument is measured, not
assumed: `stems` scores Basic Pitch on each stem against the passage.

    python -m brasscribe_eval.small_tab_bench synthesize [--data DIR]    the passages (FluidSynth)
    python -m brasscribe_eval.small_tab_bench prepare [--data DIR]       run the models (GPU)
    python -m brasscribe_eval.small_tab_bench stems [--data DIR]         which stem carries the instrument
    python -m brasscribe_eval.small_tab_bench report [--data DIR]        per-group numbers

It runs on a computer that has the SoundFont and the models, not in CI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

SET = "small-tab"
SOUNDFONT = "soundfonts/MuseScore_General.sf2"
SR = 44100
MODES = ("song", "instrument")
BARS = 12
GUITAR = (64, 59, 55, 50, 45, 40)
# group -> (the job's instrument and tuning, SoundFont bank and program, the open strings from string 1,
# chord shapes as frets from string 1 (None: not played), a scale for the melody)
GROUPS = {
    "ukulele-high-g": ({"instrument": "ukulele", "tuning": "high-g"}, (8, 24), (69, 64, 60, 67),
                       {"C": (3, 0, 0, 0), "Am": (0, 0, 0, 2), "F": (0, 1, 0, 2), "G": (2, 3, 2, 0)}, (60, 62, 64, 65, 67, 69, 71, 72)),
    "ukulele-low-g": ({"instrument": "ukulele", "tuning": "low-g"}, (8, 24), (69, 64, 60, 55),
                      {"C": (3, 0, 0, 0), "Am": (0, 0, 0, 2), "F": (0, 1, 0, 2), "G": (2, 3, 2, 0)}, (55, 57, 59, 60, 62, 64, 65, 67)),
    "ukulele-baritone": ({"instrument": "ukulele-baritone"}, (8, 24), (64, 59, 55, 50),
                         {"G": (3, 0, 0, 0), "Em": (0, 0, 0, 2), "C": (0, 1, 0, 2), "D": (2, 3, 2, 0)}, (50, 52, 54, 55, 57, 59, 60, 62)),
    "mandolin": ({"instrument": "mandolin"}, (16, 25), (76, 69, 62, 55),
                 {"G": (3, 2, 0, 0), "C": (0, 3, 2, 0), "D": (2, 0, 0, 2), "Em": (0, 2, 2, 0)}, (62, 64, 66, 67, 69, 71, 73, 74, 76, 78, 79)),
    # A guitar's open chords, picked and strummed: what GuitarSet's players do not play. The rules for the
    # overtones over ringing strings were chosen on the first two groups and on GuitarSet's players 00 to 02;
    # the two "heldout" groups (other chords, another preset, other tempos) are only reported.
    "guitar-nylon": ({"instrument": "guitar-6"}, (0, 24), GUITAR,
                     {"C": (0, 1, 0, 2, 3, None), "Am": (0, 1, 2, 2, 0, None), "F": (1, 1, 2, 3, 3, 1), "G": (3, 0, 0, 0, 2, 3)},
                     (52, 53, 55, 57, 59, 60, 62, 64, 65, 67)),
    "guitar-steel": ({"instrument": "guitar-6"}, (0, 25), GUITAR,
                     {"G": (3, 0, 0, 0, 2, 3), "Em": (0, 0, 0, 2, 2, 0), "C": (0, 1, 0, 2, 3, None), "D": (2, 3, 2, 0, None, None)},
                     (55, 57, 59, 60, 62, 64, 66, 67, 69, 71)),
    "guitar-nylon-heldout": ({"instrument": "guitar-6"}, (0, 24), GUITAR,
                             {"A": (0, 2, 2, 2, 0, None), "E": (0, 0, 1, 2, 2, 0), "Dm": (1, 3, 2, 0, None, None),
                              "Bm": (2, 3, 4, 4, 2, None), "E7": (0, 3, 1, 0, 2, 0)},
                             (57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 74)),
    "guitar-clean-heldout": ({"instrument": "guitar-6"}, (0, 27), GUITAR,
                             {"D": (2, 3, 2, 0, None, None), "A7": (0, 2, 0, 2, 0, None), "Em7": (0, 3, 0, 2, 2, 0),
                              "F#m": (2, 2, 2, 4, 4, 2), "Cadd9": (0, 3, 0, 2, 3, None)},
                             (50, 52, 54, 55, 57, 59, 61, 62, 64, 66, 67)),
}
# Held out: other chords (one shape up the neck each), other scales, other tempos and one more pattern, a
# melody high on the top string over a ringing chord. These groups are reported, not tuned on (see the module docstring for the exceptions).
HELDOUT = "-heldout"
_UKE = {"D": (0, 2, 2, 2), "Bm": (2, 2, 2, 4), "G7": (2, 1, 2, 0), "A": (0, 0, 1, 2), "C at 5": (7, 8, 7, 5)}
GROUPS.update({
    "ukulele-high-g" + HELDOUT: (GROUPS["ukulele-high-g"][0], (8, 24), (69, 64, 60, 67), _UKE, (62, 64, 66, 67, 69, 71, 73, 74, 76, 78)),
    "ukulele-low-g" + HELDOUT: (GROUPS["ukulele-low-g"][0], (8, 24), (69, 64, 60, 55), _UKE, (57, 59, 61, 62, 64, 66, 67, 69, 71)),
    "ukulele-baritone" + HELDOUT: (GROUPS["ukulele-baritone"][0], (8, 24), (64, 59, 55, 50),
                                   {"A": (0, 2, 2, 2), "F#m": (2, 2, 2, 4), "D7": (2, 1, 2, 0), "E": (0, 0, 1, 2), "G at 5": (7, 8, 7, 5)},
                                   (52, 54, 56, 57, 59, 61, 62, 64, 66)),
    "mandolin" + HELDOUT: (GROUPS["mandolin"][0], (16, 25), (76, 69, 62, 55),
                           {"A": (0, 0, 2, 2), "E": (0, 2, 2, 1), "F": (1, 0, 3, 5), "A again": (0, 0, 2, 2), "G at 7": (7, 5, 5, 7),
                            "D at 10": (10, 9, 7, 7)},
                           (57, 59, 61, 62, 64, 66, 68, 69, 71, 73, 74, 76, 78, 80, 81)),
})
PATTERNS = ("melody", "strummed", "picked")
HELDOUT_PATTERNS = (*PATTERNS, "chord-melody")
# A mandolin's tremolo: each note of a melody repeated in sixteenths. Under a bass and drums the separator puts it
# in its `other` stem, not `guitar` (engine tab.py, Heard.empty_stem_fallback). Scored apart, under the group's
# TREMOLO key, and skipped where it has not been rendered: the group's other numbers do not move when it is.
TREMOLO = "tremolo"
EXTRA_PATTERNS = {"mandolin": (TREMOLO,), "mandolin-heldout": (TREMOLO,)}
# The held-out passages a rule was chosen on: the chord-melody and strummed ones were used to choose the rule
# that tells a chord heard again under a melody from a strum struck again (engine tab.py, RING_*). They are
# scored apart, under the group's DEV key, and the group's held-out numbers are from its other passages. Not
# for every rule: which instruments the rule for overtones in a line SwiftF0 did not hear applies to (engine
# tab.py, Heard.unheard_overtones_out) was chosen while looking at all the held-out passages, these others too.
DEVELOPMENT = ("chord-melody", "strummed")
DEV = "_dev"
TEMPOS = {"melody": 104.0, "strummed": 92.0, "picked": 80.0, TREMOLO: 96.0}
HELDOUT_TEMPOS = {"melody": 116.0, "strummed": 84.0, "picked": 72.0, "chord-melody": 88.0, TREMOLO: 84.0}
GUITAR_HELDOUT_TEMPOS = {"melody": 118.0, "strummed": 86.0, "picked": 70.0, "chord-melody": 88.0}
SUITES = {"ukulele": ("ukulele-high-g", "ukulele-low-g", "ukulele-baritone",
                      "ukulele-high-g" + HELDOUT, "ukulele-low-g" + HELDOUT, "ukulele-baritone" + HELDOUT),
          "mandolin": ("mandolin", "mandolin" + HELDOUT),
          "guitar-rendered": ("guitar-nylon", "guitar-steel", "guitar-nylon" + HELDOUT, "guitar-clean" + HELDOUT)}


def patterns(group: str) -> tuple[str, ...]:
    return (HELDOUT_PATTERNS if group.endswith(HELDOUT) else PATTERNS) + EXTRA_PATTERNS.get(group, ())


def tempo(group: str, pattern: str) -> float:
    if not group.endswith(HELDOUT):
        return TEMPOS[pattern]
    return (GUITAR_HELDOUT_TEMPOS if group.startswith("guitar") else HELDOUT_TEMPOS)[pattern]
# How far each preset sounds from the pitch it is sent (bank, program -> semitones), pinned. sounding_shift reads it
# reliably on one note at a time only: on the rendered melodies its ratio is 0.001 to 0.003 against a threshold of
# 0.25, on the strums 0.10 to 0.32, so a strummed passage would be taken an octave off. synthesize checks the pin
# on each melody.
SOUNDING = {(8, 24): 0, (16, 25): 0, (0, 24): 0, (0, 25): 0, (0, 27): 0}
STEMS = ("guitar", "other", "piano", "vocals")  # where a plucked instrument could land; bass and drums are not asked
FILES = {"instrument": {"beats": "alone.beats", "bp": "alone-bp.mid", "sw": "alone-sw.mid"}}


def passage(group: str, pattern: str, bpm: float) -> list[dict]:
    """A passage for the group's instrument: {pitch, onset, offset} and, where the shape says it, the string.
    BARS bars of 4/4 after one bar's rest."""
    _, _, strings, shapes, scale = GROUPS[group]
    beat = 60 / bpm
    names = list(shapes)
    notes: list[dict] = []

    def add(pitch: int, at: float, length: float, string: int | None = None) -> None:
        notes.append({"pitch": int(pitch), "onset": round((4 + at) * beat, 6), "offset": round((4 + at + length) * beat, 6),
                      **({"string": string} if string else {})})

    for bar in range(BARS):
        at = 4 * bar
        shape = shapes[names[bar % len(names)]]
        chord = [(strings[i] + f, i + 1) for i, f in enumerate(shape) if f is not None]
        if pattern == "melody":  # eighths up and down the scale, a held note to end the bar
            run = [scale[(bar + k) % len(scale)] if k < 4 else scale[(bar + 6 - k) % len(scale)] for k in range(6)]
            for k, p in enumerate(run):
                add(p, at + k / 2, 0.45)
            add(scale[bar % len(scale)], at + 3, 0.9)
        elif pattern == TREMOLO:  # a melody in half notes, each picked in thirty-seconds
            for half in range(2):
                p = scale[(bar + 3 * half) % len(scale)]
                for k in range(16):
                    add(p, at + 2 * half + k / 8, 0.11)
        elif pattern == "chord-melody":  # the chord struck once and left to ring; a melody at frets 12 to 15 of the top string
            for j, (p, s) in enumerate(chord[::-1]):
                add(p, at + 0.012 * j * bpm / 60, 0.9 if s == 1 else 3.8, s)
            for k, fret in enumerate((12, 14, 15, 14, 12, 14)):
                add(strings[0] + fret, at + 1 + k / 2, 0.45, 1)
        elif pattern == "strummed":  # down, down-up, up-down-up: the lowest-numbered string last on a down stroke
            for k, when in enumerate((0, 1, 1.5, 2.5, 3, 3.5)):
                down = k in (0, 1, 4)
                order = chord[::-1] if down else chord
                for j, (p, s) in enumerate(order):
                    add(p, at + when + 0.012 * j * bpm / 60, 0.45, s)
        else:  # picked: each string of the shape in turn, ringing on
            order = ([chord[3], chord[1], chord[2], chord[0], chord[2], chord[1], chord[2], chord[0]] if len(strings) == 4 else
                     [chord[-1], chord[2], chord[1], chord[0], chord[1], chord[2], chord[1], chord[0]])  # the bass, then the top three
            for k, (p, s) in enumerate(order):
                add(p, at + k / 2, 0.9, s)
    return sorted(notes, key=lambda n: (n["onset"], n["pitch"]))


def midi_file(tracks: list[tuple[int, int, bool, list[tuple[int, float, float, int]]]], bpm: float):
    """A MIDI file of tracks of (bank, program, is_drum, [(pitch, onset, offset, velocity)]). The bank is
    selected before the program: the Ukulele and Mandolin presets are in banks of their own, and a file that
    says it the other way round plays a guitar."""
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    tempo = mido.bpm2tempo(bpm)
    for index, (bank, program, is_drum, notes) in enumerate(tracks):
        channel = 9 if is_drum else (index if index < 9 else index + 1)
        events = [(0, 0, mido.Message("control_change", channel=channel, control=0, value=bank)),
                  (0, 1, mido.Message("program_change", channel=channel, program=program))]
        for p, a, b, v in notes:
            events.append((int(round(mido.second2tick(a, 480, tempo))), 3, mido.Message("note_on", channel=channel, note=p, velocity=v)))
            events.append((int(round(mido.second2tick(b, 480, tempo))), 2, mido.Message("note_off", channel=channel, note=p, velocity=0)))
        track = mido.MidiTrack()
        if index == 0:
            track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        last = 0
        for tick, _, message in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(message.copy(time=tick - last))
            last = tick
        mid.tracks.append(track)
    return mid


def _render(tracks: list[tuple[int, int, bool, list[tuple[int, float, float, int]]]], bpm: float, soundfont: Path, dst: Path) -> None:
    """FluidSynth's render of midi_file(tracks, bpm)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.mid"
        midi_file(tracks, bpm).save(str(path))
        subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.6", "-r", str(SR), "-F", str(dst),
                        str(soundfont), str(path)], check=True, capture_output=True)


def synthesize(data: Path, only_new: bool = False) -> list[Path]:
    """Every group's passages: reference.json, alone.wav (the instrument) and mix.wav (with a bass and drums).
    `only_new`: leave the passages that are already there as they are."""
    import soundfile as sf

    from .bass_tab_bench import sounding_shift

    soundfont = Path(data) / SOUNDFONT
    made = []
    for group, (params, (bank, program), strings, shapes, _) in GROUPS.items():
        for pattern in patterns(group):
            bpm = tempo(group, pattern)
            beat = 60 / bpm
            notes = passage(group, pattern, bpm)
            lead = (bank, program, False, [(n["pitch"], n["onset"], n["offset"], 92) for n in notes])
            drums, bass = [], []
            roots = [min(strings[k] + f for k, f in enumerate(shape) if f is not None) % 12 + 36 for shape in shapes.values()]
            for bar in range(BARS + 1):
                t = 4 * bar * beat
                drums += [(36, t + k * 2 * beat, t + k * 2 * beat + 0.1, 100) for k in range(2)]
                drums += [(38, t + (1 + 2 * k) * beat, t + (1 + 2 * k) * beat + 0.1, 90) for k in range(2)]
                drums += [(42, t + k * beat / 2, t + k * beat / 2 + 0.05, 60) for k in range(8)]
                if bar:
                    root = roots[(bar - 1) % len(roots)]
                    bass += [(root, t + k * beat, t + (k + 0.9) * beat, 90) for k in range(4)]
            dest = Path(data) / "eval" / SET / f"{group}-{pattern}"
            if only_new and (dest / "reference.json").exists():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            _render([lead], bpm, soundfont, dest / "alone.wav")
            _render([lead, (0, 33, False, bass), (0, 0, True, drums)], bpm, soundfont, dest / "mix.wav")
            # The reference is what sounds: the preset's pinned shift, checked on the render of the group's melody.
            shift = SOUNDING[(bank, program)]
            if pattern == "melody":
                audio, sr = sf.read(str(dest / "alone.wav"), dtype="float64", always_2d=True)
                heard = sounding_shift(audio.mean(axis=1), sr, notes, lowest=0)
                if heard != shift:
                    raise RuntimeError(f"{group}: the melody sounds {heard} semitones from what it was sent, not {shift}")
            (dest / "reference.json").write_text(json.dumps({
                "group": group, "pattern": pattern, "style": pattern, "player": "synthesized", "params": params,
                "written_to_sounding": shift, "tempo_bpm": bpm, "beats_per_bar": 4,
                "notes": [{**n, "pitch": n["pitch"] + shift} for n in notes]}))
            made.append(dest)
    return made


def entries(data: Path, groups: tuple[str, ...] | None = None) -> list[Path]:
    root = Path(data) / "eval" / SET
    found = sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []
    return [p for p in found if groups is None or json.loads((p / "reference.json").read_text())["group"] in groups]


def song_files(stem: str) -> dict[str, str]:
    """The files a `song` run reads when the instrument is taken from the separator's `stem`."""
    return {"beats": "song.beats", "bp": f"song-{stem}-bp.mid", "sw": f"song-{stem}-sw.mid"}


def prepare(entry: Path) -> None:
    """Run the models an entry still lacks: Beat This! on both renders, Basic Pitch and SwiftF0 on the
    instrument alone (retuned as a whole recording is), the separator on the mix, and both transcribers on
    each of its stems that could hold the instrument."""
    from .suites import _run_adapter, _run_retuned

    alone, mix = entry / "alone.wav", entry / "mix.wav"
    if not (entry / "alone.beats").exists():
        _run_adapter("beat-this", alone, entry / "alone.beats")
    if not (entry / "song.beats").exists():
        _run_adapter("beat-this", mix, entry / "song.beats")
    for key, tool in (("bp", "basic-pitch"), ("sw", "swift-f0")):
        if not (entry / FILES["instrument"][key]).exists():
            _run_retuned(tool, alone, entry / FILES["instrument"][key])
    if not all((entry / f"song-{stem}.wav").exists() for stem in STEMS):
        with tempfile.TemporaryDirectory() as tmp:
            _run_adapter("separator", mix, Path(tmp))
            for stem in STEMS:
                found = [p for p in Path(tmp).glob("*.wav") if f"_({stem})_" in p.name.lower()]
                if not found:
                    raise RuntimeError(f"the separator wrote no {stem} stem for {entry.name}")
                shutil.move(str(found[0]), entry / f"song-{stem}.wav")
    for stem in STEMS:
        files = song_files(stem)
        if not (entry / files["bp"]).exists():
            _run_adapter("basic-pitch", entry / f"song-{stem}.wav", entry / files["bp"])
        if not (entry / files["sw"]).exists():
            _run_adapter("swift-f0", entry / f"song-{stem}.wav", entry / files["sw"])


def stem_scores(data: Path, groups: tuple[str, ...] | None = None) -> dict[str, dict[str, float]]:
    """For each stem the separator writes: how much of the instrument Basic Pitch finds in it, and how much
    of what it finds there is the instrument (recall and precision of onset and pitch, means over the passages)."""
    from brasscribe_engine import bass_tab

    from .score import score

    rows: dict[str, list[dict]] = {stem: [] for stem in STEMS}
    for entry in entries(data, groups):
        ref = json.loads((entry / "reference.json").read_text())
        if ref["pattern"] in EXTRA_PATTERNS.get(ref["group"], ()):  # scored apart: the stems' numbers stay as they were
            continue
        ref = ref["notes"]
        for stem in STEMS:
            est = [n for n in bass_tab.load_transcription(entry / song_files(stem)["bp"]) if n["offset"] - n["onset"] >= 0.06]
            rows[stem].append(score(ref, est))
    return {stem: {k: float(np.mean([r[k] for r in rs])) for k in ("onset_r", "onset_p", "onset_f1")} for stem, rs in rows.items() if rs}


def split(group: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The parts a group is scored in: (label suffix, patterns). A held-out group's DEVELOPMENT passages apart, and
    each of the group's EXTRA_PATTERNS apart."""
    extra = EXTRA_PATTERNS.get(group, ())
    own = tuple(p for p in patterns(group) if p not in extra)
    apart = tuple((f"_{p}", (p,)) for p in extra)
    if not group.endswith(HELDOUT):
        return (("", own), *apart)
    return (("", tuple(p for p in own if p not in DEVELOPMENT)), (DEV, DEVELOPMENT), *apart)


def evaluate(data: Path, groups: tuple[str, ...], mode: str, clean: bool = True, stem: str | None = None,
             only: tuple[str, ...] | None = None) -> tuple[dict[str, float], list[dict]]:
    """The passages of `groups` in one recording mode, through the tab profile's own stages. `stem`: the
    separator's stem a `song` run reads (default: the one the profile reads, tab.stem_to_read). `only`: the
    patterns to score (default all)."""
    from brasscribe_engine import tab

    from .guitar_tab_bench import score_tab, summarize, tab_of

    rows = []
    for entry in entries(data, groups):
        ref = json.loads((entry / "reference.json").read_text())
        if only is not None and ref["pattern"] not in only:
            continue
        params = {**ref["params"], "recording": mode}
        instrument = ref["params"]["instrument"]
        files = FILES["instrument"] if mode == "instrument" else song_files(
            stem or tab.stem_to_read(instrument, lambda s, e=entry: e / f"song-{s}.wav", entry / "mix.wav"))
        rows.append({"excerpt": entry.name, **score_tab(ref, tab_of(entry, clean, params, files))})
    return summarize(rows), rows


def report(data: Path) -> str:
    lines = []
    for suite, groups in SUITES.items():
        lines.append(f"{suite}: stems " + "  ".join(f"{s} r={v['onset_r']:.2f} p={v['onset_p']:.2f}" for s, v in stem_scores(data, groups).items()))
        for group in groups:
            for part, only in split(group):
                for mode in MODES:
                    for label, clean in (("straight", False), ("rules", True)):
                        out, _ = evaluate(data, (group,), mode, clean, only=only)
                        lines.append(f"  {group + part:22s} {mode:10s} {label:8s} " + " ".join(f"{k}={v:.3f}" for k, v in out.items()))
    return "\n".join(lines)


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["synthesize", "prepare", "stems", "report"])
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--only-new", action="store_true", help="synthesize: keep the passages that are already rendered")
    args = ap.parse_args()
    if args.command == "synthesize":
        for d in synthesize(args.data, args.only_new):
            notes = json.loads((d / "reference.json").read_text())["notes"]
            print(f"{d.name}: {len(notes)} notes, {min(n['pitch'] for n in notes)} to {max(n['pitch'] for n in notes)}")
    elif args.command == "prepare":
        for d in entries(args.data):
            prepare(d)
            print(d.name, "ready", flush=True)
    elif args.command == "stems":
        for suite, groups in SUITES.items():
            for stem, v in stem_scores(args.data, groups).items():
                print(f"{suite:9s} {stem:7s} recall {v['onset_r']:.3f} precision {v['onset_p']:.3f} F1 {v['onset_f1']:.3f}")
    else:
        print(report(args.data))


if __name__ == "__main__":
    main()
