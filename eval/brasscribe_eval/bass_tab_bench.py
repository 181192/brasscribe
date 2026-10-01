"""Bass tab benchmark: the engine's bass-tab profile on Slakh bass lines, in both recording modes.

    song        the full mix: Beat This! on the mix, the BS-RoFormer SW bass stem, Basic Pitch on it
    instrument  the bass stem alone: Beat This! and Basic Pitch on it (retuned to A = 440 as any whole recording)

The eval set is built from Slakh tracks with exactly one Bass-class stem (`build`), under
<data>/eval/slakh-bass/<track>/: reference.json and, once the models have run (`prepare`, live mode),
their outputs. The notes then go through the profile's own code (brasscribe_engine.bass_tab) and the
Rust core, so the numbers are those of a job's tab.json.

The reference is at sounding pitch. Slakh writes bass an octave above where its patches sound; that is
checked per stem on the rendered audio (sounding_shift) rather than assumed, and stored with the reference.

    python -m brasscribe_eval.bass_tab_bench build <slakh root> [--data DIR]     reference.json per track
    python -m brasscribe_eval.bass_tab_bench prepare <slakh root> [--data DIR]   run the models (GPU)
    python -m brasscribe_eval.bass_tab_bench report [--data DIR]                 per-track numbers
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

def sounding_shift(audio: np.ndarray, sr: int, notes: list[dict], max_notes: int = 60) -> int:
    """0 when the stem sounds at the MIDI's pitches, -12 when it sounds an octave below them.

    For each longer note, the spectrum of its sound is read at the partials an octave-lower tone would
    add between those of the written pitch (0.5 f, 1.5 f, 2.5 f). A tone at the written pitch has
    nothing there; one an octave lower has its odd partials there. The median over the notes decides."""
    ratios = []
    long = [n for n in notes if n["offset"] - n["onset"] >= 0.2 and n["pitch"] >= 36][:max_notes]
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


def prepare(entry: Path, track: Path) -> None:
    """Run the models an entry still lacks: Beat This!, the separator, Basic Pitch and SwiftF0."""
    from .suites import _run_adapter, _run_retuned

    ref = json.loads((entry / "reference.json").read_text())
    mix, stem = track / "mix.wav", track / "stems" / f"{ref['stem']}.wav"
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
                raise RuntimeError(f"the separator wrote no bass stem for {track.name}")
            shutil.move(str(found[0]), separated)
    if not (entry / "song-bp.mid").exists():
        _run_adapter("basic-pitch", separated, entry / "song-bp.mid")  # a stem is not retuned
    if not (entry / "alone-bp.mid").exists():
        _run_retuned("basic-pitch", stem, entry / "alone-bp.mid")
    if not (entry / "song-sw.mid").exists():
        _run_adapter("swift-f0", separated, entry / "song-sw.mid")
    if not (entry / "alone-sw.mid").exists():
        _run_adapter("swift-f0", stem, entry / "alone-sw.mid")


def entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / SET
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


# ---------------------------------------------------------------- the tab and its score

def tab_of(entry: Path, mode: str, params: dict | None = None) -> dict:
    """tab.json's content for one entry, made by the profile's own stages from the cached model outputs."""
    from brasscribe_engine import bass_tab

    files = FILES[mode]
    opts = bass_tab.options(params or {})
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
           "violations": float(len(tab["violations"])), "octave_moved": float(tab.get("octave_notes_moved", 0))}
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
    # A triplet's length on a note that starts on the 16th grid and is followed by one: a bracket over a straight line.
    out["triplet_lengths"] = float(np.mean([n["start"] % 6 == 0 and n["dur"] % 6 != 0
                                            and (i + 1 == len(notes) or notes[i + 1]["start"] % 6 == 0) for i, n in enumerate(notes)]))
    frets = [n["fret"] for n in notes if n["fret"] is not None]
    fretted = [f for f in frets if f > 0]  # an open string leaves the hand where it is
    out["hand_travel"] = float(np.mean(np.abs(np.diff(fretted)))) if len(fretted) > 1 else 0.0
    out["high_fret_share"] = float(np.mean([f > HIGH_FRET for f in frets])) if frets else 0.0
    return out


MEANS = ("onset_f1", "onset_p", "onset_r", "octave_err_rate", "out_of_range", "hand_travel", "high_fret_share",
         "doubt_share", "triplet_lengths", "tempo_ok", "tempo_ok_level", "meter_ok")


def evaluate(data: Path, mode: str, params: dict | None = None) -> tuple[dict[str, float], list[dict]]:
    """Mean metrics over the set for one recording mode, and the per-track rows."""
    rows = []
    for entry in entries(data):
        ref = json.loads((entry / "reference.json").read_text())
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
    for mode in MODES:
        out, rows = evaluate(data, mode, params)
        lines.append(f"{mode}: " + "  ".join(f"{k} {v:.3f}" for k, v in out.items()))
        for r in rows:
            lines.append(f"  {r['track']}  f1 {r['onset_f1']:.3f} p {r['onset_p']:.3f} r {r['onset_r']:.3f}  oct {r['octave_err_rate']:.3f}"
                         f"  oor {r['out_of_range']:.3f}  travel {r['hand_travel']:.2f}  high {r['high_fret_share']:.2f}"
                         f"  doubt {int(r['doubt_marked_wrong'])}/{int(r['doubt_marked'])} of {int(r['wrong'])} wrong"
                         f"  moved {int(r['octave_moved'])}  tempo {r.get('tempo_ok', '-')}  meter {r.get('meter_ok', '-')}")
    return "\n".join(lines)


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "prepare", "report"])
    ap.add_argument("slakh", type=Path, nargs="?")
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()
    if args.command == "build":
        for d in build(args.slakh, args.data):
            ref = json.loads((d / "reference.json").read_text())
            print(f"{d.name}: {len(ref['notes'])} notes, {ref['program']}, written to sounding {ref['written_to_sounding']}, "
                  f"{ref['tempo_bpm']} BPM, {ref['beats_per_bar']} beats a bar")
    elif args.command == "prepare":
        for d in entries(args.data):
            prepare(d, args.slakh / d.name)
            print(d.name, "ready", flush=True)
    else:
        print(report(args.data))


if __name__ == "__main__":
    main()
