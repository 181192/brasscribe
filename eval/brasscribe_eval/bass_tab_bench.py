"""Bass tab benchmark: the engine's bass-tab profile on Slakh bass lines, in both recording modes.

    song        the full mix: Beat This! on the mix, the BS-RoFormer SW bass stem, Basic Pitch on it
    instrument  the bass stem alone: Beat This! and Basic Pitch on it (retuned to A = 440 as any whole recording)

The eval set is built from Slakh tracks with exactly one Bass-class stem (`build`), under
<data>/eval/slakh-bass/<track>/: reference.json and, once the models have run (`prepare`, live mode),
their outputs. The notes then go through the profile's own code (brasscribe_engine.bass_tab) and the
Rust core, so the numbers are those of a job's tab.json.

The reference is at sounding pitch. Slakh writes bass an octave above where its patches sound; that is
checked per stem on the rendered audio (sounding_shift) rather than assumed, and stored with the reference.

A second set covers what Slakh's lines never reach, the bottom of the instrument: lines written here
between B0 and E2 and rendered with FluidSynth and the MuseScore General SoundFont (`synthesize`), alone
and under drums and a keyboard. Its numbers are reported apart from Slakh's, as low_e and low_b.

A third set, `phone`, is every Slakh bass stem and every synthesized line alone with its bottom cut as a phone's
microphone would (build_phone), for the octave check: whether a line heard above where a bass plays was heard
there or really is there. It is reported apart, by cut.

All three sets are rendered instruments. Nothing here measures a real recording.

    python -m brasscribe_eval.bass_tab_bench build <slakh root> [--data DIR]     reference.json per Slakh track
    python -m brasscribe_eval.bass_tab_bench synthesize [--data DIR]             the low-register set (FluidSynth)
    python -m brasscribe_eval.bass_tab_bench prepare <slakh root> [--data DIR]   run the models (GPU)
    python -m brasscribe_eval.bass_tab_bench build-phone <slakh root> [--data DIR]  the bass alone as a phone hears it
    python -m brasscribe_eval.bass_tab_bench prepare-phone [--data DIR]          run the models on it
    python -m brasscribe_eval.bass_tab_bench report [--data DIR]                 per-track numbers

It runs on a computer that has the data and the models, not in CI: `brasscribe bench bass-tab` scores
what `prepare` left next to the data, `--mode live` builds and prepares what is missing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

SET = "slakh-bass"
SOURCE = "slakh/babyslakh_16k"
MODES = ("song", "instrument")
ONSET_TOL = 0.05
HIGH_FRET = 9  # a note above this fret is up the neck: the share of them is a readability number
MIN_NOTES = 40  # a reference line shorter than this says little
TEMPO_TOL = 0.04
DOUBT_BELOW = 0.4  # target-fretted's default: a note below this confidence gets the "?" mark
SECOND = True  # SwiftF0 confirms Basic Pitch's notes, as in the profile; False scores Basic Pitch's amplitude alone


# ---------------------------------------------------------------- the reference

def sounding_shift(audio: np.ndarray, sr: int, notes: list[dict], max_notes: int = 60, lowest: int = 36) -> int:
    """0 when the stem sounds at the MIDI's pitches, -12 when it sounds an octave below them.

    For each longer note, the spectrum of its sound is read at the partials an octave-lower tone would
    add between those of the written pitch (0.5 f, 1.5 f, 2.5 f). A tone at the written pitch has
    nothing there; one an octave lower has its odd partials there. The median over the notes decides."""
    ratios = []
    long = [n for n in notes if n["offset"] - n["onset"] >= 0.2 and n["pitch"] >= lowest][:max_notes]
    for n in long:
        a, b = int((n["onset"] + 0.03) * sr), int(min(n["offset"], n["onset"] + 0.6) * sr)
        seg = audio[a:b]
        if len(seg) < 0.12 * sr:
            continue
        size = 1 << 15
        mag = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), size))
        f = 440 * 2 ** ((n["pitch"] - 69) / 12)

        def peak(hz: float) -> float:
            k = int(round(hz * size / sr))
            w = max(2, int(round(0.03 * hz * size / sr)))
            return float(mag[max(0, k - w):k + w + 1].max()) if k + w < len(mag) else 0.0

        written = sum(peak(f * h) for h in (1, 2, 3))
        between = sum(peak(f * h) for h in (0.5, 1.5, 2.5))
        if written + between > 0:
            ratios.append(between / (written + between))
    return -12 if ratios and float(np.median(ratios)) > 0.25 else 0


def build(slakh: Path, data: Path) -> list[Path]:
    """reference.json for every track of `slakh` with exactly one Bass stem that has enough notes."""
    import pretty_midi
    import soundfile as sf
    import yaml

    made = []
    for track in sorted(p for p in Path(slakh).iterdir() if (p / "metadata.yaml").exists()):
        meta = yaml.safe_load((track / "metadata.yaml").read_text())
        bass = [sid for sid, stem in meta["stems"].items()
                if stem["inst_class"] == "Bass" and (track / "stems" / f"{sid}.wav").exists()]
        if len(bass) != 1:
            continue
        sid = bass[0]
        pm = pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{sid}.mid"))
        notes = sorted(({"pitch": n.pitch, "onset": float(n.start), "offset": float(n.end)}
                        for inst in pm.instruments for n in inst.notes), key=lambda n: (n["onset"], n["pitch"]))
        if len(notes) < MIN_NOTES:
            continue
        audio, sr = sf.read(str(track / "stems" / f"{sid}.wav"), dtype="float64", always_2d=True)
        shift = sounding_shift(audio.mean(axis=1), sr, notes)
        whole = pretty_midi.PrettyMIDI(str(track / "all_src.mid"))
        _, tempi = whole.get_tempo_changes()
        meters = whole.time_signature_changes
        dest = Path(data) / "eval" / SET / track.name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "reference.json").write_text(json.dumps({
            "stem": sid, "program": meta["stems"][sid]["midi_program_name"], "written_to_sounding": shift,
            "tempo_bpm": float(tempi[0]) if len(tempi) == 1 else None,  # None: the tempo changes
            "beats_per_bar": int(meters[0].numerator) if len(meters) == 1 else (4 if not meters else None),
            "notes": [{**n, "pitch": n["pitch"] + shift} for n in notes]}, indent=1))
        made.append(dest)
    return made


# ---------------------------------------------------------------- the models' outputs

# What each mode reads, next to reference.json. `*-sw.mid` is SwiftF0 on the same audio as Basic Pitch.
FILES = {"song": {"beats": "song.beats", "bp": "song-bp.mid", "sw": "song-sw.mid"},
         "instrument": {"beats": "alone.beats", "bp": "alone-bp.mid", "sw": "alone-sw.mid"}}


def audio_of(entry: Path, slakh: Path | None) -> tuple[Path, Path]:
    """The full mix and the bass alone of an entry: a Slakh track's files, or the synthesized ones kept with it."""
    ref = json.loads((entry / "reference.json").read_text())
    if "stem" in ref:
        if slakh is None:
            raise FileNotFoundError(f"{entry.name} needs the Slakh tracks")
        return Path(slakh) / entry.name / "mix.wav", Path(slakh) / entry.name / "stems" / f"{ref['stem']}.wav"
    return entry / "mix.wav", entry / "bass.wav"


def prepare(entry: Path, mix: Path, stem: Path) -> None:
    """Run the models an entry still lacks: Beat This!, the separator, Basic Pitch and SwiftF0."""
    from .suites import _run_adapter, _run_retuned

    if not (entry / "song.beats").exists():
        _run_adapter("beat-this", mix, entry / "song.beats")
    if not (entry / "alone.beats").exists():
        _run_adapter("beat-this", stem, entry / "alone.beats")
    separated = entry / "song-bass.wav"
    if not separated.exists():
        with tempfile.TemporaryDirectory() as tmp:
            _run_adapter("separator", mix, Path(tmp))
            found = [p for p in Path(tmp).glob("*.wav") if "_(bass)_" in p.name.lower()]
            if not found:
                raise RuntimeError(f"the separator wrote no bass stem for {entry.name}")
            shutil.move(str(found[0]), separated)
    if not (entry / "song-bp.mid").exists():
        _run_adapter("basic-pitch", separated, entry / "song-bp.mid")  # a stem is not retuned
    if not (entry / "alone-bp.mid").exists():
        _run_retuned("basic-pitch", stem, entry / "alone-bp.mid")
    if not (entry / "song-sw.mid").exists():
        _run_adapter("swift-f0", separated, entry / "song-sw.mid")
    if not (entry / "alone-sw.mid").exists():
        _run_retuned("swift-f0", stem, entry / "alone-sw.mid")  # the same retuned recording as Basic Pitch


def entries(data: Path, eval_set: str = SET) -> list[Path]:
    root = Path(data) / "eval" / eval_set
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


# ---------------------------------------------------------------- the low register, synthesized

# Slakh's bass lines sit between B1 and G3. Nothing in them is on the E string below the 7th fret, on a
# five-string's B string, or under SwiftF0's floor (F#1). These lines are: written here, rendered with
# FluidSynth and the MuseScore General SoundFont (MIT), alone and under drums and a keyboard.
SYNTH_SET = "synth-bass"
SOUNDFONT = "soundfonts/MuseScore_General.sf2"
SYNTH_SR = 44100
# group -> (lowest root, the job's instrument). low-e: E1 to B1 and a little above, a four-string's bottom
# string. low-b: B0 to E1 and a little above, a five-string's.
GROUPS = {"low-e": (28, "bass-4"), "low-b": (23, "bass-5")}
PATTERNS = ("eighths", "walk", "octaves", "syncopated")
PROGRESSION = (0, 5, 7, 3)  # semitones over the lowest root, one per bar
BARS = 16


def synth_line(group: str, pattern: str, bpm: float) -> list[dict]:
    """A bass line in the group's register: {pitch, onset, offset}, 4/4, BARS bars, from beat 0 after one bar's rest."""
    low, _ = GROUPS[group]
    beat = 60 / bpm
    notes = []

    def add(pitch: int, at: float, length: float) -> None:
        notes.append({"pitch": int(pitch), "onset": round((4 + at) * beat, 6), "offset": round((4 + at + length * 0.9) * beat, 6)})

    for bar in range(BARS):
        root = low + PROGRESSION[bar % 4]
        at = 4 * bar
        if pattern == "eighths":  # the root in eighths, a fifth to end the bar
            for k in range(8):
                add(root + (7 if k == 7 else 0), at + k / 2, 0.5)
        elif pattern == "walk":  # quarters up the scale and back
            for k, step in enumerate((0, 2, 4, 5) if bar % 2 == 0 else (7, 5, 4, 2)):
                add(root + step, at + k, 1)
        elif pattern == "octaves":  # root and octave in eighths
            for k in range(8):
                add(root + (12 if k % 2 else 0), at + k / 2, 0.5)
        else:  # dotted quarter, eighth tied over, two eighths
            for start, length, step in ((0, 1.5, 0), (1.5, 1.0, 0), (2.5, 0.5, 7), (3, 0.5, 0), (3.5, 0.5, 5)):
                add(root + step, at + start, length)
    return notes


def _render(tracks: list[tuple[int, bool, list[tuple[int, float, float, int]]]], bpm: float, soundfont: Path, dst: Path) -> None:
    """FluidSynth's render of tracks of (program, is_drum, [(pitch, onset, offset, velocity)])."""
    import subprocess

    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    for program, is_drum, notes in tracks:
        inst = pretty_midi.Instrument(program=program, is_drum=is_drum)
        inst.notes = [pretty_midi.Note(velocity=v, pitch=p, start=a, end=b) for p, a, b, v in notes]
        pm.instruments.append(inst)
    with tempfile.TemporaryDirectory() as tmp:
        mid = Path(tmp) / "x.mid"
        pm.write(str(mid))
        subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.6", "-r", str(SYNTH_SR), "-F", str(dst),
                        str(soundfont), str(mid)], check=True, capture_output=True)


def synthesize(data: Path) -> list[Path]:
    """The low-register entries: reference.json, bass.wav (the bass alone) and mix.wav (with drums and a keyboard)."""
    import soundfile as sf

    soundfont = Path(data) / SOUNDFONT
    made = []
    for group, (low, instrument) in GROUPS.items():
        for i, pattern in enumerate(PATTERNS):
            bpm = (96.0, 120.0, 108.0, 84.0)[i]
            beat = 60 / bpm
            line = synth_line(group, pattern, bpm)
            bass = (33, False, [(n["pitch"], n["onset"], n["offset"], 100) for n in line])  # Electric Bass (finger)
            drums, keys = [], []
            for bar in range(BARS + 1):
                t = 4 * bar * beat
                drums += [(36, t + k * 2 * beat, t + k * 2 * beat + 0.1, 100) for k in range(2)]  # kick on 1 and 3
                drums += [(38, t + (1 + 2 * k) * beat, t + (1 + 2 * k) * beat + 0.1, 90) for k in range(2)]  # snare on 2 and 4
                drums += [(42, t + k * beat / 2, t + k * beat / 2 + 0.05, 60) for k in range(8)]  # hi-hat eighths
                if bar:
                    root = 48 + (low + PROGRESSION[(bar - 1) % 4]) % 12
                    keys += [(root + iv, t, t + 3.8 * beat, 70) for iv in (0, 4, 7)]  # a triad around middle C
            dest = Path(data) / "eval" / SYNTH_SET / f"{group}-{pattern}"
            dest.mkdir(parents=True, exist_ok=True)
            _render([bass], bpm, soundfont, dest / "bass.wav")
            _render([bass, (0, True, drums), (4, False, keys)], bpm, soundfont, dest / "mix.wav")
            audio, sr = sf.read(str(dest / "bass.wav"), dtype="float64", always_2d=True)
            shift = sounding_shift(audio.mean(axis=1), sr, line, lowest=0)
            (dest / "reference.json").write_text(json.dumps({
                "group": group, "pattern": pattern, "params": {"instrument": instrument}, "written_to_sounding": shift,
                "tempo_bpm": bpm, "beats_per_bar": 4, "notes": [{**n, "pitch": n["pitch"] + shift} for n in line]}, indent=1))
            made.append(dest)
    return made


# ---------------------------------------------------------------- the bass alone, as a phone hears it

# What the octave check is for: a recording whose fundamental is weak, so that the transcribers hear the line an
# octave high. A phone's microphone and its recording chain roll off the bottom; that is imitated here with a
# high-pass filter (PHONE_CUTS, Hz, PHONE_ORDER-th order Butterworth) on every Slakh bass stem (also those of
# the tracks with two bass stems, which `build` leaves out, among them the synth lines that really sit high) and
# on the synthesized low lines. Only the bass-alone mode exists here. The cut is a stand-in for a phone; a real
# phone recording with its notes annotated would be better evidence and was not found.
PHONE_SET = "phone-bass"
PHONE_CUTS = (100, 200)
PHONE_ORDER = 4
PHONE_FILES = {"phone": FILES["instrument"]}


def _phone_filter(audio: np.ndarray, sr: int, cut: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt

    out = sosfilt(butter(PHONE_ORDER, cut, btype="highpass", fs=sr, output="sos"), audio, axis=0)
    return out / max(1e-9, float(np.max(np.abs(out)))) * 0.9


def build_phone(slakh: Path | None, data: Path) -> list[Path]:
    """The phone set: per bass line and cut, bass.wav (filtered), reference.json (the unfiltered line's), and
    `cut_hz`. Each Slakh entry also gets a `cut_hz` 0 entry, the stem as rendered, so a line that sits high
    is there unfiltered too."""
    import pretty_midi
    import soundfile as sf
    import yaml

    sources = []  # (name, audio, sample rate, reference without the notes' shift applied, notes)
    for track in sorted(p for p in Path(slakh).iterdir() if (p / "metadata.yaml").exists()) if slakh else ():
        meta = yaml.safe_load((track / "metadata.yaml").read_text())
        for sid, stem in meta["stems"].items():
            wav = track / "stems" / f"{sid}.wav"
            if stem["inst_class"] != "Bass" or not wav.exists():
                continue
            pm = pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{sid}.mid"))
            notes = sorted(({"pitch": n.pitch, "onset": float(n.start), "offset": float(n.end)}
                            for inst in pm.instruments for n in inst.notes), key=lambda n: (n["onset"], n["pitch"]))
            if len(notes) < MIN_NOTES:
                continue
            audio, sr = sf.read(str(wav), dtype="float64", always_2d=True)
            shift = sounding_shift(audio.mean(axis=1), sr, notes)
            sources.append((f"{track.name}-{sid}", audio, sr, {"program": stem["midi_program_name"], "written_to_sounding": shift},
                            [{**n, "pitch": n["pitch"] + shift} for n in notes]))
    for entry in entries(data, SYNTH_SET):
        ref = json.loads((entry / "reference.json").read_text())
        audio, sr = sf.read(str(entry / "bass.wav"), dtype="float64", always_2d=True)
        sources.append((entry.name, audio, sr, {"group": ref["group"], "params": ref["params"]}, ref["notes"]))
    made = []
    for name, audio, sr, about, notes in sources:
        for cut in ((0,) if "program" in about else ()) + PHONE_CUTS:
            dest = Path(data) / "eval" / PHONE_SET / f"{name}-hp{cut}"
            dest.mkdir(parents=True, exist_ok=True)
            sf.write(str(dest / "bass.wav"), _phone_filter(audio, sr, cut) if cut else audio, sr)
            (dest / "reference.json").write_text(json.dumps({**about, "cut_hz": cut, "notes": notes}, indent=1))
            made.append(dest)
    return made


def prepare_phone(entry: Path) -> None:
    """Beat This!, Basic Pitch and SwiftF0 on a phone entry's bass, as the profile runs them on a recording."""
    from .suites import _run_adapter, _run_retuned

    f = PHONE_FILES["phone"]
    if not (entry / f["beats"]).exists():
        _run_adapter("beat-this", entry / "bass.wav", entry / f["beats"])
    if not (entry / f["bp"]).exists():
        _run_retuned("basic-pitch", entry / "bass.wav", entry / f["bp"])
    if not (entry / f["sw"]).exists():
        _run_retuned("swift-f0", entry / "bass.wav", entry / f["sw"])


# ---------------------------------------------------------------- the tab and its score

def tab_of(entry: Path, mode: str, params: dict | None = None) -> dict:
    """tab.json's content for one entry, made by the profile's own stages from the cached model outputs."""
    from brasscribe_engine import bass_tab

    files = {**FILES, **PHONE_FILES}[mode]
    # An entry may say what the job would be given: a five-string for a line below E1.
    opts = bass_tab.options({**json.loads((entry / "reference.json").read_text()).get("params", {}), **(params or {})})
    doc = bass_tab.transcribed_line(bass_tab.load_transcription(entry / files["bp"]),
                                    np.loadtxt(entry / files["beats"], ndmin=2), opts["octave"],
                                    bass_tab.load_transcription(entry / files["sw"]) if SECOND else None)
    doc["reference_pitch"] = None
    return bass_tab.fingered(doc, opts)


def score_tab(ref: dict, tab: dict) -> dict:
    """One tab against its reference: the notes, the song's tempo and meter, and how the tab plays."""
    import mir_eval

    from .score import score, to_arrays

    notes = tab["notes"]
    est = [{"pitch": n["pitch"], "onset": n["onset_s"], "offset": n["offset_s"]} for n in notes]
    s = score(ref["notes"], est)
    out = {"onset_f1": s["onset_f1"], "onset_p": s["onset_p"], "onset_r": s["onset_r"], "octave_err_rate": s["octave_err_rate"],
           "notes": float(len(notes)), "out_of_range": float(np.mean([n["out_of_range"] for n in notes])),
           "violations": float(len(tab["violations"])), "octave_moved": float(tab.get("octave_notes_moved", 0)),
           "line_moved": float(tab.get("octave_shift", 0) != 0)}
    # Which written notes are right: matched to a reference note in onset and pitch.
    ri, rp = to_arrays(ref["notes"])
    ei, ep = to_arrays(est)
    right = {j for _, j in mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None)}
    doubt = [n["confidence"] < DOUBT_BELOW for n in notes]
    wrong = [j not in right for j in range(len(notes))]
    out["doubt_share"] = float(np.mean(doubt))
    out["doubt_marked"], out["doubt_marked_wrong"] = float(sum(doubt)), float(sum(d and w for d, w in zip(doubt, wrong)))
    out["wrong"] = float(sum(wrong))
    if ref.get("tempo_bpm"):
        ratio = tab["tempo_bpm"] / ref["tempo_bpm"]
        out["tempo_ok"] = float(abs(ratio - 1) <= TEMPO_TOL)
        out["tempo_ok_level"] = float(any(abs(ratio / k - 1) <= TEMPO_TOL for k in (0.5, 1, 2)))
    if ref.get("beats_per_bar"):
        out["meter_ok"] = float(tab["meter"]["beats"] == ref["beats_per_bar"])
        if ref.get("tempo_bpm"):  # the bar as it sounds: its length in seconds, whatever the level and the count
            bar, true = tab["meter"]["beats"] / tab["tempo_bpm"], ref["beats_per_bar"] / ref["tempo_bpm"]
            out["bar_ok"] = float(abs(bar / true - 1) <= TEMPO_TOL)
    # A triplet's length on a note that starts on the 16th grid and is followed by one: a bracket over a straight line.
    out["triplet_lengths"] = float(np.mean([n["start"] % 6 == 0 and n["dur"] % 6 != 0
                                            and (i + 1 == len(notes) or notes[i + 1]["start"] % 6 == 0) for i, n in enumerate(notes)]))
    frets = [n["fret"] for n in notes if n["fret"] is not None]
    fretted = [f for f in frets if f > 0]  # an open string leaves the hand where it is
    out["hand_travel"] = float(np.mean(np.abs(np.diff(fretted)))) if len(fretted) > 1 else 0.0
    out["high_fret_share"] = float(np.mean([f > HIGH_FRET for f in frets])) if frets else 0.0
    return out


MEANS = ("onset_f1", "onset_p", "onset_r", "octave_err_rate", "out_of_range", "hand_travel", "high_fret_share",
         "doubt_share", "triplet_lengths", "tempo_ok", "tempo_ok_level", "meter_ok", "bar_ok", "line_moved")


def evaluate(data: Path, mode: str, params: dict | None = None, eval_set: str = SET,
             group: str | None = None, cut: int | None = None) -> tuple[dict[str, float], list[dict]]:
    """Mean metrics over a set (or one group of it, or the phone set's entries of one cut) for one recording
    mode, and the per-track rows."""
    rows = []
    for entry in entries(data, eval_set):
        ref = json.loads((entry / "reference.json").read_text())
        if (group is None or ref.get("group") == group) and (cut is None or ref.get("cut_hz") == cut):
            rows.append({"track": entry.name, **score_tab(ref, tab_of(entry, mode, params))})
    out = {k: float(np.mean([r[k] for r in rows if k in r])) for k in MEANS}
    out["violations"] = float(sum(r["violations"] for r in rows))
    out["octave_moved"] = float(sum(r["octave_moved"] for r in rows))
    marked, marked_wrong, wrong = (sum(r[k] for r in rows) for k in ("doubt_marked", "doubt_marked_wrong", "wrong"))
    # Of the notes marked doubtful, how many are wrong; of the wrong notes, how many are marked.
    out["doubt_precision"] = marked_wrong / marked if marked else 0.0
    out["doubt_recall"] = marked_wrong / wrong if wrong else 0.0
    out["tracks"] = float(len(rows))
    return out, rows


def report(data: Path, params: dict | None = None) -> str:
    lines = []
    for eval_set, mode in [(e, m) for e in (SET, SYNTH_SET) if entries(data, e) for m in MODES]:
        out, rows = evaluate(data, mode, params, eval_set)
        lines.append(f"{eval_set} {mode}: " + "  ".join(f"{k} {v:.3f}" for k, v in out.items()))
        for r in rows:
            lines.append(f"  {r['track']}  f1 {r['onset_f1']:.3f} p {r['onset_p']:.3f} r {r['onset_r']:.3f}  oct {r['octave_err_rate']:.3f}"
                         f"  oor {r['out_of_range']:.3f}  travel {r['hand_travel']:.2f}  high {r['high_fret_share']:.2f}"
                         f"  doubt {int(r['doubt_marked_wrong'])}/{int(r['doubt_marked'])} of {int(r['wrong'])} wrong"
                         f"  moved {int(r['octave_moved'])}  tempo {r.get('tempo_ok', '-')}  meter {r.get('meter_ok', '-')}")
    return "\n".join(lines)


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "synthesize", "prepare", "build-phone", "prepare-phone", "report"])
    ap.add_argument("slakh", type=Path, nargs="?")
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()
    if args.command == "build":
        for d in build(args.slakh, args.data):
            ref = json.loads((d / "reference.json").read_text())
            print(f"{d.name}: {len(ref['notes'])} notes, {ref['program']}, written to sounding {ref['written_to_sounding']}, "
                  f"{ref['tempo_bpm']} BPM, {ref['beats_per_bar']} beats a bar")
    elif args.command == "synthesize":
        for d in synthesize(args.data):
            ref = json.loads((d / "reference.json").read_text())
            pitches = [n["pitch"] for n in ref["notes"]]
            print(f"{d.name}: {len(pitches)} notes, {min(pitches)} to {max(pitches)}, written to sounding {ref['written_to_sounding']}")
    elif args.command == "build-phone":
        print(f"{len(build_phone(args.slakh, args.data))} phone entries")
    elif args.command == "prepare-phone":
        for d in entries(args.data, PHONE_SET):
            prepare_phone(d)
            print(d.name, "ready", flush=True)
    elif args.command == "prepare":
        for d in entries(args.data) + entries(args.data, SYNTH_SET):
            prepare(d, *audio_of(d, args.slakh))
            print(d.name, "ready", flush=True)
    else:
        print(report(args.data))


if __name__ == "__main__":
    main()
