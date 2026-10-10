"""Guitar tab benchmark: the engine's tab profile with a guitar, on GuitarSet.

GuitarSet (Xi, Bittner, Pauwels, Ye, Bello, ISMIR 2018; CC BY 4.0, Zenodo 3371780) is six players each
playing 30 lead sheets twice, once comping (chords) and once soloing (a single line), recorded with a
hexaphonic pickup, so every note is annotated with the string it was played on. The benchmark reads the
`audio_mono-mic` recordings (the guitar alone, through a microphone) and the JAMS annotations.

    python -m brasscribe_eval.guitar_tab_bench build <guitarset root> [--data DIR]    reference.json per excerpt
    python -m brasscribe_eval.guitar_tab_bench prepare <guitarset root> [--data DIR] [--only beats|notes] [--reverse]
                                                                                     run the models
    python -m brasscribe_eval.guitar_tab_bench build-songs <slakh root> / prepare-songs <slakh root>
                                                                                     guitars in a song (Slakh)
    python -m brasscribe_eval.guitar_tab_bench build-idmt <IDMT-SMT-GUITAR_V2> / prepare-idmt <IDMT-SMT-GUITAR_V2>
                                                                                     other guitars (IDMT-SMT-Guitar)
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
# The folder's name while the references were being corrected (seven stems had been an octave low), when
# `slakh-guitar` still held the earlier ones. build-songs takes the models' outputs over from it, and a data folder
# where it is still a folder of its own (not moved to SONG_SET) is read from it. Moving a data folder to the new
# name: move the earlier `slakh-guitar` aside, run build-songs (it writes the same references to SONG_SET and copies
# the models' outputs over), then move SONG_SET_BEFORE aside; a link of that name to SONG_SET keeps older checkouts
# that share the folder reading the same tracks.
SONG_SET_BEFORE = "slakh-guitar-as-written"
SONG_SOURCE = "slakh/babyslakh_16k"
SONG_FILES = {"beats": "song.beats", "bp": "song-bp.mid", "sw": "song-sw.mid"}


def build_songs(slakh: Path, data: Path) -> list[Path]:
    """reference.json for every Slakh track with a guitar: the notes of its Guitar stems, as its MIDI has them.

    The stems sound at the MIDI's pitches. (The bass bench reads from the audio whether a patch sounds an
    octave lower; on a guitar's chords that reading is not reliable, and it had put seven of these stems an
    octave down. Basic Pitch on each of the 43 stems by itself agrees with the MIDI as written, F1 0.4 to
    0.96 against 0 to 0.38 an octave lower, for every stem it hears at all.)"""
    import shutil

    import pretty_midi
    import yaml

    from .bass_tab_bench import MIN_NOTES

    made = []
    for track in sorted(p for p in Path(slakh).iterdir() if (p / "metadata.yaml").exists()):
        meta = yaml.safe_load((track / "metadata.yaml").read_text())
        notes, programs = [], []
        for sid, stem in meta["stems"].items():
            if stem["inst_class"] != "Guitar" or not (track / "stems" / f"{sid}.wav").exists():
                continue
            pm = pretty_midi.PrettyMIDI(str(track / "MIDI" / f"{sid}.mid"))
            own = [{"pitch": n.pitch, "onset": float(n.start), "offset": float(n.end)} for inst in pm.instruments for n in inst.notes]
            if not own:
                continue
            notes += own
            programs.append(stem["midi_program_name"])
        if len(notes) < MIN_NOTES:
            continue
        whole = pretty_midi.PrettyMIDI(str(track / "all_src.mid"))
        _, tempi = whole.get_tempo_changes()
        meters = whole.time_signature_changes
        dest = Path(data) / "eval" / SONG_SET / track.name
        dest.mkdir(parents=True, exist_ok=True)
        # The models' outputs do not depend on the reference: the ones made for the earlier references are taken over.
        earlier = Path(data) / "eval" / SONG_SET_BEFORE / track.name
        for name in (*SONG_FILES.values(), "song-guitar.wav"):
            if (earlier / name).exists() and not (dest / name).exists():
                shutil.copy2(earlier / name, dest / name)
        (dest / "reference.json").write_text(json.dumps({
            "style": "song", "player": "slakh", "programs": programs, "guitars": len(programs),
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


def song_root(data: Path) -> Path:
    """The folder of the Slakh song set: SONG_SET, or SONG_SET_BEFORE in a data folder not yet moved to the new name."""
    before = Path(data) / "eval" / SONG_SET_BEFORE
    return before if before.is_dir() and not before.is_symlink() else Path(data) / "eval" / SONG_SET


def song_entries(data: Path) -> list[Path]:
    root = song_root(data)
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


# ---------------------------------------------------------------- other guitars (IDMT-SMT-Guitar)

# GuitarSet is one acoustic guitar through one microphone. IDMT-SMT-Guitar (Fraunhofer IDMT, CC BY-NC-ND 4.0,
# Zenodo 7544110; not redistributed here) has three electric guitars recorded direct, with every note and
# its string annotated: short licks (dataset 2: single lines with bends, slides and vibrato, and chords,
# played with the fingers, with a pick and muted) and five longer pieces (dataset 3, three of them
# polyphonic fingerstyle). The licks of two of the guitars (AR, FS) are with the material the rules are chosen
# on; the third guitar's licks (LP) and the pieces are only reported.
IDMT_SET = "idmt-guitar"
IDMT_TUNE = ("AR", "FS")


def idmt_reference(xml: Path, style: str) -> dict:
    """The notes of an IDMT-SMT-Guitar annotation. Its strings count from the low E (1); a tab's from the high e (1)."""
    import xml.etree.ElementTree as ET

    root = ET.parse(str(xml)).getroot()
    notes = []
    for e in root.iter("event"):
        get = {c.tag: (c.text or "").strip() for c in e}
        note = {"pitch": int(round(float(get["pitch"]))), "onset": float(get["onsetSec"]), "offset": float(get["offsetSec"])}
        if get.get("stringNumber", "").isdigit() and 1 <= int(get["stringNumber"]) <= STRINGS:
            note["string"] = STRINGS + 1 - int(get["stringNumber"])
        notes.append(note)
    player = Path(xml).stem.split("_")[0] if style == "lick" else "piece"
    return {"player": player, "style": style, "split": "tune" if player in IDMT_TUNE else "report",
            "tempo_bpm": None, "beats_per_bar": None, "notes": sorted(notes, key=lambda n: (n["onset"], n["pitch"]))}


def idmt_sources(root: Path) -> list[tuple[Path, Path, str]]:
    """(annotation, audio, style) of the licks and the pieces under the unpacked IDMT-SMT-GUITAR_V2."""
    root = Path(root)
    found = [(x, root / "dataset2" / "audio" / f"{x.stem}.wav", "lick") for x in sorted((root / "dataset2" / "annotation").glob("*Lick*.xml"))]
    found += [(x, root / "dataset3" / "audio" / f"{x.stem}.wav", "piece") for x in sorted((root / "dataset3" / "annotation").glob("*.xml"))]
    return [f for f in found if f[1].exists()]


def build_idmt(root: Path, data: Path) -> list[Path]:
    made = []
    for xml, _, style in idmt_sources(root):
        ref = idmt_reference(xml, style)
        if len(ref["notes"]) < 4:
            continue
        dest = Path(data) / "eval" / IDMT_SET / f"{style}-{xml.stem}"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "reference.json").write_text(json.dumps(ref))
        made.append(dest)
    return made


def idmt_entries(data: Path) -> list[Path]:
    root = Path(data) / "eval" / IDMT_SET
    return sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else []


def evaluate_idmt(data: Path, split: str, clean: bool = True, params: dict | None = None) -> tuple[dict[str, float], list[dict]]:
    """IDMT-SMT-Guitar's excerpts of one split (`tune` or `report`), the guitar alone. A lick of a few seconds
    can be too short for the beat tracker: the engine refuses it, and `refused` counts those."""
    rows, refused = [], 0
    for entry in idmt_entries(data):
        ref = json.loads((entry / "reference.json").read_text())
        if ref["split"] == split and all((entry / f).exists() for f in FILES.values()):
            try:
                rows.append({"excerpt": entry.name, **score_tab(ref, tab_of(entry, clean, params))})
            except ValueError:
                refused += 1
    return ({**summarize(rows), "refused": float(refused)} if rows else {}), rows


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
                           opts["instrument"], opts["octave"], bass_tab.load_transcription(entry / files["sw"]), clean=clean,
                           chords=opts["chords"])
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
    # A unison (one pitch on two strings of a chord) is matched either way round: its strings are compared as a set.
    placed = [(i, j) for i, j in pairs if notes[j]["string"] is not None and "string" in ref["notes"][i]]
    together: dict[tuple, tuple[list, list]] = {}
    for i, j in placed:
        mine, theirs = together.setdefault((notes[j]["start"], notes[j]["pitch"]), ([], []))
        mine.append(notes[j]["string"])
        r = ref["notes"][i]
        theirs += [o["string"] for o in ref["notes"] if o["pitch"] == r["pitch"] and abs(o["onset"] - r["onset"]) <= ONSET_TOL and "string" in o]
    out["placed"], out["same_string"] = float(len(placed)), float(sum(len(set(mine) & set(theirs)) for mine, theirs in together.values()))
    out["ref_strings"] = float(sum("string" in n for n in ref["notes"]))
    out["notes"] = float(len(notes))
    out["out_of_range"] = float(np.mean([n["out_of_range"] for n in notes])) if notes else 0.0
    out["violations"] = float(len(tab["violations"]))
    out["unplayable_dropped"] = float(tab.get("unplayable_dropped", 0))
    out["leftovers_dropped"] = float(tab.get("leftovers_dropped", 0))
    out["octave_moved"] = float(tab.get("octave_notes_moved", 0))
    inferred = [j for j, n in enumerate(notes) if n.get("inferred")]
    out["inferred"], out["inferred_right"] = float(len(inferred)), float(sum(j in right_est for j in inferred))
    doubt = [n["confidence"] < 0.4 for n in notes]
    wrong = [j not in right_est for j in range(len(notes))]
    out["doubt_marked"], out["doubt_marked_wrong"], out["wrong"] = float(sum(doubt)), float(sum(d and w for d, w in zip(doubt, wrong))), float(sum(wrong))
    if ref.get("tempo_bpm"):
        ratio = tab["tempo_bpm"] / ref["tempo_bpm"]
        out["tempo_ok"] = float(abs(ratio - 1) <= TEMPO_TOL)
        out["tempo_ok_level"] = float(any(abs(ratio / k - 1) <= TEMPO_TOL for k in (0.5, 1, 2)))
    if ref.get("beats_per_bar"):
        out["meter_ok"] = float(tab["meter"]["beats"] == ref["beats_per_bar"])
        if ref.get("tempo_bpm"):  # the bar as it sounds: its length in seconds, whatever the level and the count
            bar, true = tab["meter"]["beats"] / tab["tempo_bpm"], ref["beats_per_bar"] / ref["tempo_bpm"]
            out["bar_ok"] = float(abs(bar / true - 1) <= TEMPO_TOL)
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
         "tempo_ok", "tempo_ok_level", "meter_ok", "bar_ok")


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
    out["inferred_share"], out["inferred_right"] = ratio("inferred", "notes"), ratio("inferred_right", "inferred")
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


def evaluate_songs(data: Path, clean: bool = True, params: dict | None = None, one_guitar: bool = False) -> tuple[dict[str, float], list[dict]]:
    """The Slakh songs' guitars, from the separator's guitar stem. `one_guitar`: only the songs with a single guitar,
    where the tab can be the part one player plays."""
    rows = []
    for entry in song_entries(data):
        if all((entry / f).exists() for f in SONG_FILES.values()):
            ref = json.loads((entry / "reference.json").read_text())
            if one_guitar and len(ref["programs"]) != 1:
                continue
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
    ap.add_argument("command", choices=["build", "prepare", "build-songs", "prepare-songs", "build-idmt", "prepare-idmt", "report"])
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
            print(f"{d.name}: {len(ref['notes'])} notes, {ref['programs']}")
    elif args.command == "build-idmt":
        print(f"{len(build_idmt(args.root, args.data))} excerpts")
    elif args.command == "prepare-idmt":
        audio = {f"{style}-{xml.stem}": wav for xml, wav, style in idmt_sources(args.root)}
        for d in idmt_entries(args.data):
            prepare(d, audio[d.name], args.only)
            print(d.name, "ready", flush=True)
    elif args.command == "prepare-songs":
        for d in song_entries(args.data):
            prepare_song(d, args.root / d.name / "mix.wav")
            print(d.name, "ready", flush=True)
    else:
        print(report(args.data))


if __name__ == "__main__":
    main()
