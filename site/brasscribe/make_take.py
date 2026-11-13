"""Make the take Brasscribe's pages are drawn from: fifteen seconds of a real brass quartet, written down by the
real engine. Everything in site/brasscribe/take/ and site/brasscribe/figures/ comes from this script.

The recording is the opening of J. S. Bach's "Ich steh an deiner Krippe hier" from ChoraleBricks v1.1.0
(S. Balke, A. Berndt, M. Müller; CC BY 4.0; https://doi.org/10.5281/zenodo.20849469): two trumpets, a baritone
and a tuba, each recorded alone, mixed here. The script checks each track's SHA-256, mixes them, checks the mix,
runs `scribe run --profile brass-band --lineup quartet` in a data folder it throws away, and keeps:

  take/       what the engine answered: composition.json, brass-band.musicxml, talking-score.json, the beats, the
              notes each of its two listeners heard before they were merged (heard.json), and take.json (the
              tracks, their checksums, the stages that ran)
  figures/    what the pages load: take.mp3 (the mix, mono), sound.json (its loudness fifty times a second),
              part-<n>.svg (each player's part engraved by Verovio, as one line), score.json (for every note its
              time, its place in the engraving and what it is: bar, beat, pitch and value)

    cargo build --release -p scribe-cli           (in core/, or set SCRIBE_CORE_CLI)
    uv run --with verovio --with numpy python site/brasscribe/make_take.py            everything, engine included
    uv run --with verovio --with numpy python site/brasscribe/make_take.py --keep     the figures again from take/

Needs the dataset under data/choralebricks (or SCRIBE_DATA), the models, ffmpeg, pixi and the core's command line.
The site's build needs none of them.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("take_tools", HERE.parent / "shared" / "take_tools.py")
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)
sha, samples, run, midi_notes, sound = tools.sha, tools.samples, tools.run, tools.midi_notes, tools.sound
TAKE, OUT = HERE / "take", HERE / "figures"
DATA = Path(os.environ.get("SCRIBE_DATA", ROOT / "data"))
SONG = "Bach_IchStehAnDeinerKrippe"
TITLE = "Ich steh an deiner Krippe hier"
SECONDS = 14.6
TRACKS = {  # the four players, and the SHA-256 of each one's track in ChoraleBricks v1.1.0
    "01_tp.wav": "48cd6bcb7caedc30e3f066fcb7761649b9bdf2854657c3c80914aac893591a17",
    "02_tp.wav": "a635e371712bd551eea3dfdada54f1be5118c1d465b342b899e7b84af3ae98b1",
    "03_bar.wav": "5be6c77c4bfcc1dadd40874f5ecd8a4521284b3f89029f2f676b8be154c52fbd",
    "04_tba.wav": "8a3d7d7f5aa96198c9724b50aee22eeb1b2f47eacb7f9ad59483f3dad7774e97",
}
MIX = "9a1edf630b6fbfa9d9ee930446c3d76ead1f59fbadcbd1411c1a9d8d5d0d1aa3"  # the SHA-256 of the mix's samples
REST = {"en": "rest", "nb": "pause"}
BAR = {"en": "Bar", "nb": "Takt"}





def mix(to: Path) -> None:
    folder = DATA / "choralebricks" / "01_AudioAndAnnotations" / SONG / "tracks"
    if not folder.is_dir():
        sys.exit(f"ChoraleBricks is not at {folder.parent.parent.parent}: download v1.1.0 from https://doi.org/10.5281/zenodo.20849469, or set SCRIBE_DATA")
    inputs = []
    for name, pinned in TRACKS.items():
        if sha(folder / name) != pinned:
            sys.exit(f"{name} is not the track of ChoraleBricks v1.1.0 this take was made from")
        inputs += ["-i", str(folder / name)]
    run("ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
        f"amix=inputs={len(TRACKS)}:normalize=0,volume=0.5,atrim=0:{SECONDS},afade=t=out:st={SECONDS - 0.4}:d=0.4", "-ac", "1", str(to))
    if samples(to) != MIX:
        sys.exit("the mix made here is not, sample for sample, the one the committed take was made from (another ffmpeg?)")



def engine(wav: Path) -> None:
    """The real engine on the mix, in a data folder that is thrown away; what it answered goes to take/."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "SCRIBE_DATA": f"{tmp}/data", "SCRIBE_MODELS": os.environ.get("SCRIBE_MODELS", str(ROOT / "models"))}
        run("pixi", "run", "scribe", "run", "--profile", "brass-band", "--lineup", "quartet", "--title", TITLE, "--no-audio",
            "--out", f"{tmp}/out", str(wav), cwd=ROOT, env=env)
        run_dir = next(Path(tmp, "data", "runs").iterdir())
        TAKE.mkdir(exist_ok=True)
        for name in ("composition.json", "brass-band.musicxml", "talking-score.json"):
            shutil.copy(Path(tmp, "out", name), TAKE)
        shutil.copy(run_dir / "stages" / "beats" / "mix.beats", TAKE)
        manifest = json.loads(Path(tmp, "out", "manifest.json").read_text())
        heard = {stage.name.split(".")[-1]: midi_notes(next(stage.glob("*.mid"))) for stage in sorted((run_dir / "stages").glob("transcribe.*"))}
        (TAKE / "heard.json").write_text(json.dumps(heard, separators=(",", ":")) + "\n")
        about = {"title": TITLE, "work": "J. S. Bach, Ich steh an deiner Krippe hier (1736)", "seconds": SECONDS,
                 "source": "ChoraleBricks v1.1.0, CC BY 4.0, https://doi.org/10.5281/zenodo.20849469",
                 "tracks": TRACKS, "mix_samples_sha256": samples(wav), "profile": manifest["profile"], "lineup": manifest["params"]["lineup"],
                 "stages": [p.name for p in sorted((run_dir / "stages").iterdir())]}
        (TAKE / "take.json").write_text(json.dumps(about, indent=1) + "\n")



def engrave(musicxml: str, seed: int, scale: int) -> str:
    import verovio

    tk = verovio.toolkit()
    tk.setOptions({"breaks": "none", "pageWidth": 60000, "adjustPageHeight": True, "adjustPageWidth": True, "header": "none",
                   "footer": "none", "scale": scale, "pageMarginLeft": 30, "pageMarginRight": 30, "pageMarginTop": 60,
                   "pageMarginBottom": 30, "svgViewBox": True, "svgRemoveXlink": True, "xmlIdSeed": seed})
    tk.loadData(musicxml)
    return tk.renderToSVG(1)


def without_group(svg: str, name: str) -> str:
    """The picture without its <g class="name"> groups, whatever they hold."""
    while (found := re.search(rf'<g id="[^"]*" class="{name}">', svg)):
        depth, at = 1, found.end()
        while depth:
            tag = re.compile(r"<g\b[^>]*?(/?)>|</g>").search(svg, at)
            depth += 0 if tag.group(1) else (-1 if tag.group(0) == "</g>" else 1)
            at = tag.end()
        svg = svg[:found.start()] + svg[at:]
    return svg


def tidy(svg: str) -> str:
    """Smaller, and coloured and lettered by the page: no layout whitespace, no ids but the glyphs' and the notes', no
    colours or faces of its own, no embedded font (it is only for the tempo's note sign, which is left out)."""
    svg = re.sub(r">\s+<", "><", svg)
    svg = re.sub(r"<desc>.*?</desc>|<style.*?</style>", "", svg, flags=re.S)
    svg = without_group(svg, "tempo")
    svg = re.sub(r'<g(?: id="[^"]*")? class="[^"]*\bplaceholder\b[^"]*">.*?</g>', "", svg)  # Verovio hides these with a stylesheet of its own
    svg = svg.replace(' color="black"', "").replace(' font-family="Times, serif"', "")
    head, defs, body = re.match(r"(.*?)(<defs>.*?</defs>)(.*)", svg, re.S).groups()
    body = re.sub(r'<g id="[^"]*" class="(?!note")', '<g class="', body)
    body = re.sub(r' (?:color|fill|stroke)="#[0-9A-Fa-f]{6}"', "", body)
    head = re.sub(r' id="[^"]*"', "", head)
    return (head + defs + body).replace(' xmlns:xlink="http://www.w3.org/1999/xlink"', "").replace(' version="1.1"', "").strip() + "\n"


def note_places(svg: str) -> list[float]:
    """Where each note is drawn, as a share of the picture's width, in the order they are written."""
    inner = float(re.search(r'class="definition-scale"[^>]*viewBox="0 0 (\d+)', svg).group(1))
    margin = float(re.search(r'class="page-margin" transform="translate\((\d+)', svg).group(1))
    return [round((margin + float(x)) / inner, 5)
            for x in re.findall(r'class="note"><g class="notehead"><use href="[^"]*" transform="translate\((-?\d+)', svg)]


def one_part(score: str, part_id: str) -> str:
    """The score with one player's part alone."""
    score = re.sub(r'<score-part id="(?!%s")[^"]*">.*?</score-part>\s*' % part_id, "", score, flags=re.S)
    score = re.sub(r"<part-group\b.*?(?:</part-group>|/>)\s*", "", score, flags=re.S)
    return re.sub(r'<part id="(?!%s")[^"]*">.*?</part>\s*' % part_id, "", score, flags=re.S)


def spoken(cli: Path, lang: str) -> dict[str, list[str]]:
    """The talking score's line for every note of every part, with its bar said in full."""
    with tempfile.TemporaryDirectory() as tmp:
        run(str(cli), "talking-score", "--musicxml", str(TAKE / "brass-band.musicxml"), "--composition", str(TAKE / "composition.json"),
            "--target", "brass", "--lang", lang, "--text", f"{tmp}/t.txt")
        text = Path(tmp, "t.txt").read_text()
    parts, name, bar = {}, None, ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and lines[i + 1] and set(lines[i + 1]) == {"="}:
            name = line
            parts[name] = []
        elif re.match(rf"{BAR[lang]}\w* \d", line):
            bar = line.split("–")[0]
        elif line.startswith("  ") and name and REST[lang] not in line:
            said = re.sub(r", tempo \d+", "", line.strip())
            parts[name].append(said[0].upper() + said[1:] if said.lower().startswith(BAR[lang].lower()) else f"{bar}, {said}")
    return parts


def figures(wav: Path) -> int:
    cli = Path(os.environ.get("SCRIBE_CORE_CLI", ROOT / "core" / "target" / "release" / "scribe-core"))
    if not cli.is_file():
        sys.exit("scribe-core is missing: cargo build --release -p scribe-cli in core/")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    run("ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "32000", "-b:a", "64k", "-map_metadata", "-1", "-bitexact", str(OUT / "take.mp3"))
    (OUT / "sound.json").write_text(json.dumps(sound(wav), separators=(",", ":")) + "\n")
    talking = json.loads((TAKE / "talking-score.json").read_text())
    composition = json.loads((TAKE / "composition.json").read_text())
    score_xml = (TAKE / "brass-band.musicxml").read_text()
    said = spoken(cli, "en")  # the talking score says which notes are uncertain
    parts = []
    for seed, part in enumerate(talking["parts"], 1):
        svg = tidy(engrave(one_part(score_xml, part["id"]), seed, 46))
        numbered = [(bar["number"], e) for bar in part["bars"] for e in bar["events"] if e["kind"] == "note"]
        events = [e for _, e in numbered]
        places = note_places(svg)
        told, doubt = iter(said[part["name"]]), []
        for e in events:
            # The second half of a tied note is said with the first.
            tied_on = e.get("tie") and e["tie"].get("stop") and not e["tie"].get("start")
            doubt.append(doubt[-1] if tied_on else int("uncertain" in next(told, "")))
        if len(events) != len(places):
            print(f'{part["name"]}: {len(events)} notes, {len(places)} drawn', file=sys.stderr)
            return 1
        seen = iter(doubt)  # the notes the talking score calls uncertain are drawn as doubtful
        svg = re.sub(r'class="note"', lambda m: 'class="note doubt"' if next(seen) else m.group(0), svg)
        (OUT / f"part-{seed}.svg").write_text(svg)
        width, height = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups()
        parts.append({"id": str(seed), "name": {"en": part["name"], "nb": part["name_nb"]},
                      "instrument": {"en": part["instrument"], "nb": part["instrument_nb"]}, "width": int(width), "height": int(height),
                      # per note: when it sounds and for how long, where it is drawn, whether it is in doubt, then what
                      # it is: bar, beat, the part of the beat (as a fraction), letter, sharp or flat, value, dots, tied on
                      "notes": [[round(e["time_s"], 3), round(e.get("performed_s") or 0, 3), x, d, bar, e["pos"]["beat"],
                                 f'{e["pos"]["num"]}/{e["pos"]["den"]}', e["written"]["step"], e["written"]["alter"], e["type"], e["dots"],
                                 int(bool(e.get("tie") and e["tie"].get("stop") and not e["tie"].get("start")))]
                                for (bar, e), x, d in zip(numbered, places, doubt)]})
        print(f'{part["name"]}: {len(events)} notes, {sum(doubt)} doubtful, {len(svg) // 1024} KB')
    score = {"title": composition["title"], "beats": composition["beat_times"], "per_bar": composition["meters"][0]["beats"], "parts": parts}
    (OUT / "score.json").write_text(json.dumps(score, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"take.mp3: {(OUT / 'take.mp3').stat().st_size // 1024} KB")
    return 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "take.wav"
        mix(wav)
        if "--keep" not in sys.argv:
            engine(wav)
        return figures(wav)


if __name__ == "__main__":
    sys.exit(main())
