"""Make the take Fretscribe's pages are drawn from: fifteen seconds of a real guitar, written down by the real
engine. Everything in site/fretscribe/take/ and site/fretscribe/figures/ comes from this script.

The recording is the opening of take 04_SS3-98-C_comp of GuitarSet (Q. Xi, R. Bittner, J. Pauwels, X. Ye,
J. P. Bello; CC BY 4.0; https://doi.org/10.5281/zenodo.3371780): a player of the set's held-out group
fingerpicking the chord progression of Pachelbel's Canon in C. The script checks the track's SHA-256, cuts the
excerpt, checks its samples, runs `scribe run --profile tab --instrument guitar-6 --recording instrument` in a
data folder it throws away, and keeps:

  take/       what the engine answered: tab.json, tab.musicxml, tab.txt, composition.json, the beats, the notes
              each of its two listeners heard (heard.json), and take.json (the track, its checksums, the stages)
  figures/    what the pages load: take.mp3 (the excerpt, mono), sound.json (its loudness fifty times a second)
              and tab-demo.json (for every tuning the viewer offers, the string and fret of each note, its other
              places and the notes with no place, as the core's own solver answers: `scribe-core fret`)

    cargo build --release -p scribe-cli       (in core/, or set SCRIBE_CORE_CLI)
    uv run --with numpy python site/fretscribe/make_take.py            everything, engine included
    uv run --with numpy python site/fretscribe/make_take.py --keep     the figures again from take/

Needs the dataset under data/guitarset (or SCRIBE_DATA), the models, ffmpeg, pixi and the core's command line.
The site's build needs none of them.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TAKE, OUT = HERE / "take", HERE / "figures"
DATA = Path(os.environ.get("SCRIBE_DATA", ROOT / "data"))
TRACK = "04_SS3-98-C_comp_mic.wav"
TRACK_SHA = "ffd315c2999a31d800ac707d330e661aa58cc2d4b6d3dd99230326860d11ca68"
EXCERPT = "5285468a350592cd56167eed88ece6ed3220095a4f2e387dd7e0b5df779a973a"  # the SHA-256 of the excerpt's samples
TITLE = "Canon progression"
SECONDS = 15.2
PRESETS = ["guitar-standard", "guitar-drop-d", "guitar-open-g", "guitar-dadgad"]


def module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    made = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(made)
    return made


tools = module(HERE.parent / "shared" / "take_tools.py")


def excerpt(to: Path) -> None:
    track = DATA / "guitarset" / "audio_mono-mic" / TRACK
    if not track.is_file():
        sys.exit(f"GuitarSet is not at {track.parent.parent}: download it from https://doi.org/10.5281/zenodo.3371780, or set SCRIBE_DATA")
    if tools.sha(track) != TRACK_SHA:
        sys.exit(f"{TRACK} is not the track of GuitarSet this take was made from")
    tools.run("ffmpeg", "-v", "error", "-y", "-i", str(track), "-t", str(SECONDS), "-af", f"afade=t=out:st={SECONDS - 0.5}:d=0.5", str(to))
    if tools.samples(to) != EXCERPT:
        sys.exit("the excerpt cut here is not, sample for sample, the one the committed take was made from (another ffmpeg?)")


def engine(wav: Path) -> None:
    """The real engine on the excerpt, in a data folder that is thrown away; what it answered goes to take/."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "SCRIBE_DATA": f"{tmp}/data", "SCRIBE_MODELS": os.environ.get("SCRIBE_MODELS", str(ROOT / "models"))}
        tools.run("pixi", "run", "scribe", "run", "--profile", "tab", "--instrument", "guitar-6", "--recording", "instrument",
                  "--title", TITLE, "--no-audio", "--out", f"{tmp}/out", str(wav), cwd=ROOT, env=env)
        run_dir = next(Path(tmp, "data", "runs").iterdir())
        TAKE.mkdir(exist_ok=True)
        for name in ("tab.json", "tab.musicxml", "tab.txt", "composition.json"):
            shutil.copy(Path(tmp, "out", name), TAKE)
        shutil.copy(run_dir / "stages" / "beats" / "mix.beats", TAKE)
        heard = {stage.name.split(".")[-1]: tools.midi_notes(next(stage.glob("*.mid")))
                 for stage in sorted((run_dir / "stages").glob("transcribe.*")) if list(stage.glob("*.mid"))}
        (TAKE / "heard.json").write_text(json.dumps(heard, separators=(",", ":")) + "\n")
        about = {"title": TITLE, "work": "A fingerpicked accompaniment over the chord progression of Pachelbel's Canon, in C", "seconds": SECONDS,
                 "source": "GuitarSet (Q. Xi, R. Bittner, J. Pauwels, X. Ye, J. P. Bello), CC BY 4.0, https://doi.org/10.5281/zenodo.3371780",
                 "track": TRACK, "track_sha256": TRACK_SHA, "excerpt_samples_sha256": tools.samples(wav), "profile": "tab", "instrument": "guitar-6",
                 "recording": "instrument", "stages": [p.name for p in sorted((run_dir / "stages").iterdir())]}
        (TAKE / "take.json").write_text(json.dumps(about, indent=1) + "\n")


def tunings() -> dict | None:
    """For every tuning the viewer offers, where the core's solver puts each note the engine wrote."""
    cli = Path(os.environ.get("SCRIBE_CORE_CLI", ROOT / "core" / "target" / "release" / "scribe-core"))
    if not cli.is_file():
        sys.exit("scribe-core is missing: cargo build --release -p scribe-cli in core/")
    tab = json.loads((TAKE / "tab.json").read_text())
    marks = module(HERE.parent / "shared" / "figures.py").doubtful((TAKE / "tab.musicxml").read_text())
    notes = [{k: n[k] for k in ("pitch", "start", "dur")} for n in tab["notes"]]
    variants = {}
    with tempfile.TemporaryDirectory() as tmp:
        for preset in PRESETS:
            request = {"instrument": {"preset": preset, "capo": 0}, "notes": notes, "options": {"style": tab["style"], "tempo_bpm": tab["tempo_bpm"]}}
            Path(tmp, "request.json").write_text(json.dumps(request))
            tools.run(str(cli), "fret", "--request", f"{tmp}/request.json", "--out", f"{tmp}/out.json")
            answer = json.loads(Path(tmp, "out.json").read_text())
            places = answer["fingering"]["notes"]
            if preset == tab["preset"] and not all((p["string"], p["fret"], p["out_of_range"]) == (n["string"], n["fret"], n["out_of_range"])
                                                   for p, n in zip(places, tab["notes"])):
                print("the solver no longer gives the take's own places: make the take again", file=sys.stderr)
                return None
            variants[f"{preset}/0"] = {
                "tuning": answer["instrument"]["tuning"]["name"],
                "open": [s["open_pitch"] for s in answer["instrument"]["tuning"]["strings"]],
                # per note: string, fret, 1 when it has no place, then its other places as string, fret pairs
                "places": [[p["string"], p["fret"], int(p["out_of_range"]), *[v for a in p["alternatives"] for v in (a["string"], a["fret"])]] for p in places],
            }
            print(f"{preset:18} {variants[f'{preset}/0']['tuning']:9} without a place: {sum(p[2] for p in variants[f'{preset}/0']['places'])}, "
                  f"left out: {sum(p[0] is None and not p[2] for p in variants[f'{preset}/0']['places'])}")
    return {"title": TITLE, "ticks_per_beat": tab["ticks_per_beat"], "meter": tab["meter"], "tempo_bpm": tab["tempo_bpm"],
            "presets": PRESETS, "capos": [0], "default": f'{tab["preset"]}/0',
            "notes": [[n["pitch"], n["start"], n["dur"], int(i in marks)] for i, n in enumerate(tab["notes"])], "variants": variants}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "take.wav"
        excerpt(wav)
        if "--keep" not in sys.argv:
            engine(wav)
        demo = tunings()
        if demo is None:
            return 1
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()
        (OUT / "tab-demo.json").write_text(json.dumps(demo, separators=(",", ":"), ensure_ascii=False) + "\n")
        (OUT / "sound.json").write_text(json.dumps(tools.sound(wav), separators=(",", ":")) + "\n")
        tools.run("ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "32000", "-b:a", "64k", "-map_metadata", "-1", "-bitexact", str(OUT / "take.mp3"))
        print(f"take.mp3: {(OUT / 'take.mp3').stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
