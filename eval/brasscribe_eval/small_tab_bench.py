"""Ukulele and mandolin tab benchmark: the engine's tab profile on passages written here and rendered.

No recordings of a ukulele or a mandolin with their notes annotated were found (OpenMIC-2018 has clips
labelled as containing either, without notes). So the passages are written in this file and rendered
with FluidSynth and the MuseScore General SoundFont (MIT), which has sampled Ukulele and Mandolin
presets: one instrument each, one player-less performance, no room. That is weak evidence, and it is
all the evidence: the rules that read the notes were set on GuitarSet (guitar_tab_bench) and are not
adjusted on these passages, so nothing here is tuned on what it reports.

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
}
PATTERNS = ("melody", "strummed", "picked")
SUITES = {"ukulele": ("ukulele-high-g", "ukulele-low-g", "ukulele-baritone"), "mandolin": ("mandolin",)}
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
        elif pattern == "strummed":  # down, down-up, up-down-up: the lowest-numbered string last on a down stroke
            for k, when in enumerate((0, 1, 1.5, 2.5, 3, 3.5)):
                down = k in (0, 1, 4)
                order = chord[::-1] if down else chord
                for j, (p, s) in enumerate(order):
                    add(p, at + when + 0.012 * j * bpm / 60, 0.45, s)
        else:  # picked: each string of the shape in turn, ringing on
            order = [chord[3], chord[1], chord[2], chord[0], chord[2], chord[1], chord[2], chord[0]]
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


def synthesize(data: Path) -> list[Path]:
    """Every group's passages: reference.json, alone.wav (the instrument) and mix.wav (with a bass and drums)."""
    import soundfile as sf

    from .bass_tab_bench import sounding_shift

    soundfont = Path(data) / SOUNDFONT
    made = []
    for group, (params, (bank, program), strings, shapes, _) in GROUPS.items():
        for i, pattern in enumerate(PATTERNS):
            bpm = (104.0, 92.0, 80.0)[i]
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
            dest.mkdir(parents=True, exist_ok=True)
            _render([lead], bpm, soundfont, dest / "alone.wav")
            _render([lead, (0, 33, False, bass), (0, 0, True, drums)], bpm, soundfont, dest / "mix.wav")
            # A preset may sound an octave from what it is sent: the reference is what sounds, read from the render.
            audio, sr = sf.read(str(dest / "alone.wav"), dtype="float64", always_2d=True)
            shift = sounding_shift(audio.mean(axis=1), sr, notes, lowest=0)
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
        ref = json.loads((entry / "reference.json").read_text())["notes"]
        for stem in STEMS:
            est = [n for n in bass_tab.load_transcription(entry / song_files(stem)["bp"]) if n["offset"] - n["onset"] >= 0.06]
            rows[stem].append(score(ref, est))
    return {stem: {k: float(np.mean([r[k] for r in rs])) for k in ("onset_r", "onset_p", "onset_f1")} for stem, rs in rows.items() if rs}


def evaluate(data: Path, groups: tuple[str, ...], mode: str, clean: bool = True, stem: str | None = None) -> tuple[dict[str, float], list[dict]]:
    """The passages of `groups` in one recording mode, through the tab profile's own stages. `stem`: the
    separator's stem a `song` run reads (default: the one the profile uses for the instrument)."""
    from brasscribe_engine import tab

    from .guitar_tab_bench import score_tab, summarize, tab_of

    rows = []
    for entry in entries(data, groups):
        ref = json.loads((entry / "reference.json").read_text())
        params = {**ref["params"], "recording": mode}
        files = FILES["instrument"] if mode == "instrument" else song_files(stem or tab.HEARD[ref["params"]["instrument"]].stem)
        rows.append({"excerpt": entry.name, **score_tab(ref, tab_of(entry, clean, params, files))})
    return summarize(rows), rows


def report(data: Path) -> str:
    lines = []
    for suite, groups in SUITES.items():
        lines.append(f"{suite}: stems " + "  ".join(f"{s} r={v['onset_r']:.2f} p={v['onset_p']:.2f}" for s, v in stem_scores(data, groups).items()))
        for group in groups:
            for mode in MODES:
                for label, clean in (("straight", False), ("rules", True)):
                    out, _ = evaluate(data, (group,), mode, clean)
                    lines.append(f"  {group:18s} {mode:10s} {label:8s} " + " ".join(f"{k}={v:.3f}" for k, v in out.items()))
    return "\n".join(lines)


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["synthesize", "prepare", "stems", "report"])
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()
    if args.command == "synthesize":
        for d in synthesize(args.data):
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
