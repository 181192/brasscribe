"""Guitar tab benchmark: the engine's tab profile with a guitar, on GuitarSet.

GuitarSet (Xi, Bittner, Pauwels, Ye, Bello, ISMIR 2018; CC BY 4.0, Zenodo 3371780) is six players each
playing 30 lead sheets twice, once comping (chords) and once soloing (a single line), recorded with a
hexaphonic pickup, so every note is annotated with the string it was played on. The benchmark reads the
`audio_mono-mic` recordings (the guitar alone, through a microphone) and the JAMS annotations.

    python -m brasscribe_eval.guitar_tab_bench build <guitarset root> [--data DIR]    reference.json per excerpt
    python -m brasscribe_eval.guitar_tab_bench prepare <guitarset root> [--data DIR] [--only beats|notes] [--reverse]
                                                                                     run the models
    python -m brasscribe_eval.guitar_tab_bench report [--data DIR]                    per-group numbers

<guitarset root> holds `annotation/*.jams` and `audio_mono-mic/*_mic.wav` as unpacked from Zenodo.

Rules are tuned on the players in TUNE and reported on the players in REPORT, apart, so a threshold
never meets the recordings it was chosen on in the numbers that are quoted.

It runs on a computer that has the data and the models, not in CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SET = "guitarset"
STYLES = ("solo", "comp")  # a single line; chords
TUNE = ("00", "01", "02")  # players whose recordings the rules were set on
REPORT = ("03", "04", "05")  # players whose recordings are reported
FILES = {"beats": "alone.beats", "bp": "alone-bp.mid", "sw": "alone-sw.mid"}
STRINGS = 6


def reference(jams: Path) -> dict:
    """The notes of a GuitarSet annotation with their strings, and the take's tempo, meter and key.

    The annotation's strings count from the low E (0); a tab's count from the high e (1)."""
    j = json.loads(Path(jams).read_text())
    notes, tempo, beats, key = [], None, [], None
    for a in j["annotations"]:
        if a["namespace"] == "note_midi":
            string = STRINGS - int(a["annotation_metadata"]["data_source"])
            for x in a["data"]:
                notes.append({"pitch": int(round(x["value"])), "onset": float(x["time"]), "offset": float(x["time"] + x["duration"]),
                              "string": string})
        elif a["namespace"] == "tempo" and a["data"]:
            tempo = float(a["data"][0]["value"])
        elif a["namespace"] == "beat_position":
            beats = [(float(x["time"]), int(x["value"]["position"]), int(x["value"]["num_beats"])) for x in a["data"]]
        elif a["namespace"] == "key_mode" and a["data"]:
            key = a["data"][0]["value"]
    name = Path(jams).stem
    return {"player": name[:2], "style": name.rsplit("_", 1)[1], "tempo_bpm": tempo, "key": key,
            "beats_per_bar": beats[0][2] if beats else None, "beats": [[t, p] for t, p, _ in beats],
            "notes": sorted(notes, key=lambda n: (n["onset"], n["pitch"]))}


def build(root: Path, data: Path) -> list[Path]:
    made = []
    for jams in sorted((Path(root) / "annotation").glob("*.jams")):
        dest = Path(data) / "eval" / SET / jams.stem
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "reference.json").write_text(json.dumps(reference(jams)))
        made.append(dest)
    return made


def entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / SET
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


def audio_of(entry: Path, root: Path) -> Path:
    return Path(root) / "audio_mono-mic" / f"{entry.name}_mic.wav"


def prepare(entry: Path, audio: Path, only: str | None = None) -> None:
    """Run the models an entry still lacks, on the guitar alone as a `recording: instrument` job hears it:
    Beat This!, and Basic Pitch and SwiftF0 on the recording retuned to A = 440."""
    from .suites import _run_adapter, _run_retuned

    if only in (None, "beats") and not (entry / FILES["beats"]).exists():
        _run_adapter("beat-this", audio, entry / FILES["beats"])
    if only in (None, "notes"):
        for key, tool in (("bp", "basic-pitch"), ("sw", "swift-f0")):
            if not (entry / FILES[key]).exists():
                _run_retuned(tool, audio, entry / FILES[key])


# ---------------------------------------------------------------- guitars in a song (Slakh)

# GuitarSet is a guitar alone. For `recording: song` the guitar is first separated from a band, and the
# only songs here with a note reference are Slakh's: the separator's guitar stem is scored against the
# notes of all the track's Guitar-class stems together (it holds all of them). No strings are known.
SONG_SET = "slakh-guitar"
SONG_SOURCE = "slakh/babyslakh_16k"
SONG_FILES = {"beats": "song.beats", "bp": "song-bp.mid", "sw": "song-sw.mid"}


def build_songs(slakh: Path, data: Path) -> list[Path]:
    """reference.json for every Slakh track with a guitar: the notes of its Guitar stems at sounding pitch."""
    import pretty_midi
    import soundfile as sf
    import yaml

    from .bass_tab_bench import MIN_NOTES, sounding_shift

    made = []
    for track in sorted(p for p in Path(slakh).iterdir() if (p / "metadata.yaml").exists()):
        meta = yaml.safe_load((track / "metadata.yaml").read_text())
        notes, programs, shifts = [], [], []
        for sid, stem in meta["stems"].items():
            if stem["inst_class"] != "Guitar" or not (track / "stems" / f"{sid}.wav").exists():
                continue
            pm = pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{sid}.mid"))
            own = [{"pitch": n.pitch, "onset": float(n.start), "offset": float(n.end)} for inst in pm.instruments for n in inst.notes]
            if not own:
                continue
            audio, sr = sf.read(str(track / "stems" / f"{sid}.wav"), dtype="float64", always_2d=True)
            shift = sounding_shift(audio.mean(axis=1), sr, sorted(own, key=lambda n: n["onset"]), lowest=40)
            notes += [{**n, "pitch": n["pitch"] + shift} for n in own]
            programs.append(stem["midi_program_name"])
            shifts.append(shift)
        if len(notes) < MIN_NOTES:
            continue
        whole = pretty_midi.PrettyMIDI(str(track / "all_src.mid"))
        _, tempi = whole.get_tempo_changes()
        meters = whole.time_signature_changes
        dest = Path(data) / "eval" / SONG_SET / track.name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "reference.json").write_text(json.dumps({
            "style": "song", "player": "slakh", "programs": programs, "written_to_sounding": shifts,
            "tempo_bpm": float(tempi[0]) if len(tempi) == 1 else None,
            "beats_per_bar": int(meters[0].numerator) if len(meters) == 1 else (4 if not meters else None),
            "notes": sorted(notes, key=lambda n: (n["onset"], n["pitch"]))}))
        made.append(dest)
    return made


def prepare_song(entry: Path, mix: Path) -> None:
    """Beat This! on the mix, the separator's guitar stem, and Basic Pitch and SwiftF0 on it (a stem is not retuned)."""
    import shutil
    import subprocess
    import tempfile

    import pretty_midi

    from .suites import _run_adapter

    if not (entry / SONG_FILES["beats"]).exists():
        _run_adapter("beat-this", mix, entry / SONG_FILES["beats"])
    separated = entry / "song-guitar.wav"
    if not separated.exists():
        with tempfile.TemporaryDirectory() as tmp:
            _run_adapter("separator", mix, Path(tmp))
            found = [p for p in Path(tmp).glob("*.wav") if "_(guitar)_" in p.name.lower()]
            if not found:
                raise RuntimeError(f"the separator wrote no guitar stem for {entry.name}")
            shutil.move(str(found[0]), separated)
    if not (entry / SONG_FILES["bp"]).exists():
        _run_adapter("basic-pitch", separated, entry / SONG_FILES["bp"])
    if not (entry / SONG_FILES["sw"]).exists():
        try:
            _run_adapter("swift-f0", separated, entry / SONG_FILES["sw"])
        except subprocess.CalledProcessError:  # it heard no single line, and writes nothing then: no second opinion
            pretty_midi.PrettyMIDI().write(str(entry / SONG_FILES["sw"]))


def song_entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / SONG_SET
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


# ---------------------------------------------------------------- the tab and its score

ONSET_TOL = 0.05
HIGH_FRET = 9
TEMPO_TOL = 0.04
CHORD = 3  # notes that start together and make a chord


def tab_of(entry: Path, clean: bool = True, params: dict | None = None, files: dict | None = None) -> dict:
    """tab.json's content for one excerpt, made by the tab profile's own stages from the cached model outputs.
    `clean` False is Basic Pitch straight to the grid: what the rules are measured against."""
    from brasscribe_engine import bass_tab, tab

    files = files or FILES
    opts = tab.options({"instrument": "guitar-6", "recording": "instrument", **(params or {})})
    doc = tab.played_notes(bass_tab.load_transcription(entry / files["bp"]), np.loadtxt(entry / files["beats"], ndmin=2),
                           opts["instrument"], opts["octave"], bass_tab.load_transcription(entry / files["sw"]), clean=clean)
    doc["reference_pitch"] = None
    return tab.fingered(doc, opts)


def _events(notes: list[dict], key: str, tol: float) -> list[list[int]]:
    """Indices of notes that start together (within `tol` of the first of them), in time order."""
    order = sorted(range(len(notes)), key=lambda i: notes[i][key])
    events: list[list[int]] = []
    for i in order:
        if events and notes[i][key] - notes[events[-1][0]][key] <= tol:
            events[-1].append(i)
        else:
            events.append([i])
    return events


def score_tab(ref: dict, tab: dict) -> dict:
    """One tab against its reference: the notes, the chords, where they are played, tempo and meter."""
    import mir_eval

    from .score import score, to_arrays

    notes = tab["notes"]
    est = [{"pitch": n["pitch"], "onset": n["onset_s"], "offset": n["offset_s"]} for n in notes]
    s = score(ref["notes"], est)
    out = {k: s[k] for k in ("onset_f1", "onset_p", "onset_r", "octave_err_rate")}
    ri, rp = to_arrays(ref["notes"])
    ei, ep = to_arrays(est)
    pairs = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None)
    right_ref, right_est = {i for i, _ in pairs}, {j for _, j in pairs}
    # Chords: the reference's notes that start three or more together, and the tab's.
    in_ref_chord = {i for e in _events(ref["notes"], "onset", ONSET_TOL) if len(e) >= CHORD for i in e}
    in_est_chord = {j for e in _events(notes, "start", 0) if len(e) >= CHORD for j in e}
    out["chord_ref"], out["chord_ref_right"] = float(len(in_ref_chord)), float(len(in_ref_chord & right_ref))
    out["chord_est"], out["chord_est_right"] = float(len(in_est_chord)), float(len(in_est_chord & right_est))
    # A chord is whole when the notes of it that were heard are written on one onset.
    est_of = dict(pairs)
    heard = [[est_of[i] for i in e if i in est_of] for e in _events(ref["notes"], "onset", ONSET_TOL) if len(e) >= CHORD]
    heard = [e for e in heard if len(e) >= 2]
    out["chords_heard"], out["chords_whole"] = float(len(heard)), float(sum(len({notes[j]["start"] for j in e}) == 1 for e in heard))
    # Where the right notes are played: the string the player used (so the fret too).
    placed = [(i, j) for i, j in pairs if notes[j]["string"] is not None and "string" in ref["notes"][i]]
    out["placed"], out["same_string"] = float(len(placed)), float(sum(notes[j]["string"] == ref["notes"][i]["string"] for i, j in placed))
    out["ref_strings"] = float(sum("string" in n for n in ref["notes"]))
    out["notes"] = float(len(notes))
    out["out_of_range"] = float(np.mean([n["out_of_range"] for n in notes])) if notes else 0.0
    out["violations"] = float(len(tab["violations"]))
    out["unplayable_dropped"] = float(tab.get("unplayable_dropped", 0))
    out["leftovers_dropped"] = float(tab.get("leftovers_dropped", 0))
    out["octave_moved"] = float(tab.get("octave_notes_moved", 0))
    doubt = [n["confidence"] < 0.4 for n in notes]
    wrong = [j not in right_est for j in range(len(notes))]
    out["doubt_marked"], out["doubt_marked_wrong"], out["wrong"] = float(sum(doubt)), float(sum(d and w for d, w in zip(doubt, wrong))), float(sum(wrong))
    if ref.get("tempo_bpm"):
        ratio = tab["tempo_bpm"] / ref["tempo_bpm"]
        out["tempo_ok"] = float(abs(ratio - 1) <= TEMPO_TOL)
        out["tempo_ok_level"] = float(any(abs(ratio / k - 1) <= TEMPO_TOL for k in (0.5, 1, 2)))
    if ref.get("beats_per_bar"):
        out["meter_ok"] = float(tab["meter"]["beats"] == ref["beats_per_bar"])
    out["triplet_lengths"] = float(np.mean([n["dur"] % 6 != 0 and n["start"] % 6 == 0 for n in notes])) if notes else 0.0
    # The hand: the lowest fretted note of each onset. An open string leaves it where it is.
    hand = []
    for e in _events(notes, "start", 0):
        frets = [notes[j]["fret"] for j in e if notes[j]["fret"]]
        if frets:
            hand.append(min(frets))
    out["hand_travel"] = float(np.mean(np.abs(np.diff(hand)))) if len(hand) > 1 else 0.0
    frets = [n["fret"] for n in notes if n["fret"] is not None]
    out["high_fret_share"] = float(np.mean([f > HIGH_FRET for f in frets])) if frets else 0.0
    return out


MEANS = ("onset_f1", "onset_p", "onset_r", "octave_err_rate", "out_of_range", "hand_travel", "high_fret_share", "triplet_lengths",
         "tempo_ok", "tempo_ok_level", "meter_ok")


def summarize(rows: list[dict]) -> dict[str, float]:
    """Means over excerpts, and the ratios that are counted over all their notes."""
    out = {k: float(np.mean([r[k] for r in rows if k in r])) for k in MEANS}

    def ratio(num: str, den: str) -> float:
        d = sum(r[den] for r in rows)
        return float(sum(r[num] for r in rows) / d) if d else 0.0

    out["chord_recall"], out["chord_precision"] = ratio("chord_ref_right", "chord_ref"), ratio("chord_est_right", "chord_est")
    # Two readings of one count: of the notes the tab has right, and of all the notes the player played (a note
    # that is missing or wrong is then on no string at all, so this one cannot be higher than the recall).
    out["string_agreement"] = ratio("same_string", "placed")
    out["string_recall"] = ratio("same_string", "ref_strings")
    out["chords_whole"] = ratio("chords_whole", "chords_heard")
    out["doubt_precision"], out["doubt_recall"] = ratio("doubt_marked_wrong", "doubt_marked"), ratio("doubt_marked_wrong", "wrong")
    out["doubt_share"] = ratio("doubt_marked", "notes")
    out["unplayable_dropped"] = ratio("unplayable_dropped", "notes")
    out["leftovers_dropped"] = ratio("leftovers_dropped", "notes")
    out["violations"] = float(sum(r["violations"] for r in rows))
    out["octave_moved"] = float(sum(r["octave_moved"] for r in rows))
    out["excerpts"] = float(len(rows))
    return out


def evaluate(data: Path, players: tuple[str, ...], style: str, clean: bool = True, params: dict | None = None,
             limit: int | None = None) -> tuple[dict[str, float], list[dict]]:
    """The excerpts of `players` in one style: summary and per-excerpt rows."""
    rows = []
    for entry in entries(data):
        ref = json.loads((entry / "reference.json").read_text())
        if ref["player"] in players and ref["style"] == style and all((entry / f).exists() for f in FILES.values()):
            rows.append({"excerpt": entry.name, **score_tab(ref, tab_of(entry, clean, params))})
            if limit and len(rows) >= limit:
                break
    return summarize(rows), rows


def evaluate_songs(data: Path, clean: bool = True, params: dict | None = None) -> tuple[dict[str, float], list[dict]]:
    """The Slakh songs' guitars, from the separator's guitar stem."""
    rows = []
    for entry in song_entries(data):
        if all((entry / f).exists() for f in SONG_FILES.values()):
            ref = json.loads((entry / "reference.json").read_text())
            rows.append({"excerpt": entry.name, **score_tab(ref, tab_of(entry, clean, params, SONG_FILES))})
    return summarize(rows), rows


def report(data: Path) -> str:
    lines = []
    for split, players in (("tune", TUNE), ("report", REPORT)):
        for style in STYLES:
            for label, clean in (("straight", False), ("rules", True)):
                out, _ = evaluate(data, players, style, clean)
                lines.append(f"{split:6s} {style:4s} {label:8s} " + " ".join(f"{k}={v:.3f}" for k, v in out.items()))
    return "\n".join(lines)


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "prepare", "build-songs", "prepare-songs", "report"])
    ap.add_argument("root", type=Path, nargs="?")
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--only", choices=["beats", "notes"])
    ap.add_argument("--reverse", action="store_true", help="prepare from the last excerpt, beside a run from the first")
    args = ap.parse_args()
    if args.command == "build":
        made = build(args.root, args.data)
        print(f"{len(made)} excerpts")
    elif args.command == "prepare":
        for d in entries(args.data)[::-1] if args.reverse else entries(args.data):
            prepare(d, audio_of(d, args.root), args.only)
            print(d.name, "ready", flush=True)
    elif args.command == "build-songs":
        for d in build_songs(args.root, args.data):
            ref = json.loads((d / "reference.json").read_text())
            print(f"{d.name}: {len(ref['notes'])} notes, {ref['programs']}, written to sounding {ref['written_to_sounding']}")
    elif args.command == "prepare-songs":
        for d in song_entries(args.data):
            prepare_song(d, args.root / d.name / "mix.wav")
            print(d.name, "ready", flush=True)
    else:
        print(report(args.data))


if __name__ == "__main__":
    main()
