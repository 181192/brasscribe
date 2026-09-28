"""Stage implementations: adapters for audio models, the reference library for the rest.

Model stages call adapters as subprocesses. Symbolic stages run the reference
modules in `brasscribe_eval` / `brasscribe_music` with the engine's own
interpreter, exactly as the song pipeline does, so the engine reproduces its
output bit for bit.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import brasscribe_eval
import brasscribe_music

from .dag import StageContext, StageFailed

MUSIC_SRC = Path(brasscribe_music.__file__).resolve().parent
EVAL_SRC = Path(brasscribe_eval.__file__).resolve().parent
THIS = Path(__file__).resolve()
PART_STYLE = MUSIC_SRC / "parts.mss"  # MuseScore style for rendering individual parts
EXPORT_CODE = (THIS, THIS.with_name("braille.py"), THIS.with_name("talking_score.py"))
SYMBOLIC_CODE = (MUSIC_SRC, EVAL_SRC, THIS, THIS.with_name("compare.py")) + ((PART_STYLE,) if PART_STYLE.exists() else ())


def _python(ctx: StageContext, module: str, *args: str) -> None:
    proc = subprocess.run([sys.executable, "-W", "ignore", "-m", module, *args], capture_output=True, text=True)
    if proc.stdout.strip():
        for line in proc.stdout.strip().splitlines()[-20:]:
            ctx.log(line)
    if proc.returncode != 0:
        raise StageFailed(ctx.stage.name, f"{module} failed: {proc.stderr[-2000:]}")


# ---------------------------------------------------------------- model stages

def beats(ctx: StageContext) -> None:
    ctx.adapter("beat-this", ctx.inputs["audio"], ctx.out / "mix.beats")


def stems_mega53(ctx: StageContext) -> None:
    ctx.adapter("mega53", ctx.inputs["audio"], ctx.out)


_SW_NAME = re.compile(r"_\(([^)]+)\)_")


def stems_sw(ctx: StageContext) -> None:
    """BS-RoFormer SW; stem files are renamed to <stem>.wav so they do not depend on the input file name."""
    with tempfile.TemporaryDirectory(dir=ctx.out.parent) as tmp:
        ctx.adapter("separator", ctx.inputs["audio"], Path(tmp))
        for p in Path(tmp).glob("*.wav"):
            m = _SW_NAME.search(p.name)
            p.rename(ctx.out / f"{m.group(1) if m else p.stem}.wav")


def transcribe(ctx: StageContext) -> None:
    ctx.adapter(ctx.stage.adapter, ctx.inputs["audio"], ctx.out / ctx.params["output"], env=ctx.params.get("env"))


# ------------------------------------------------------------- symbolic stages

def layers(ctx: StageContext) -> None:
    """Solo / bass / drums from Mega-53, orchestra as the residual (brasscribe_eval.layers.build)."""
    from brasscribe_eval import layers as L

    L.build(ctx.inputs["audio"], ctx.inputs["trumpet"].parent, ctx.out)


def _view(files: dict[str, Path], where: Path) -> Path:
    """A directory of symlinks with the names the reference scripts expect."""
    where.mkdir(parents=True, exist_ok=True)
    for name, src in files.items():
        try:
            (where / name).symlink_to(src.resolve())
        except OSError:  # no symlink privilege (Windows)
            shutil.copy2(src, where / name)
    return where


def _stable_musicxml(ctx: StageContext) -> None:
    """Deterministic part/instrument ids, so an unchanged arrangement has unchanged bytes (and downstream cache hits)."""
    from .compare import stable_ids

    for xml in [ctx.out / "brass-band.musicxml", *sorted((ctx.out / "parts").glob("*.musicxml"))]:
        if xml.exists():
            xml.write_text(stable_ids(xml.read_text()))


_HELP: dict[str, str] = {}


def _supported(module: str) -> str:
    """The module's --help text (cached): which arrangement flags this arranger accepts."""
    if module not in _HELP:
        proc = subprocess.run([sys.executable, "-W", "ignore", "-m", module, "--help"], capture_output=True, text=True)
        _HELP[module] = proc.stdout
    return _HELP[module]


def _arrangement_flags(ctx: StageContext, module: str) -> list[str]:
    """--lineup / --difficulty / --key / --transpose for the job's non-default options.

    An option the arranger does not implement yet fails the stage, except difficulty: it is
    accepted as a parameter (it is part of the cache key) and logged as not applied."""
    opts = ctx.params.get("arrangement") or {}
    help_text = _supported(module) if opts else ""
    flags = []
    for name, value in opts.items():
        flag = f"--{name}"
        if re.search(rf"{flag}\b", help_text):
            flags += [flag, str(value)]
        elif name == "difficulty":
            ctx.log(f"difficulty {value!r} recorded; {module} does not apply it yet")
        else:
            raise StageFailed(ctx.stage.name, f"{module} does not support {flag} yet")
    return flags


def arrange_layered(ctx: StageContext) -> None:
    names = {k: v for k, v in ctx.inputs.items() if k.endswith((".mid", ".npz", ".wav"))}
    with tempfile.TemporaryDirectory(dir=ctx.out.parent) as tmp:
        view = _view(names, Path(tmp) / "layers")
        for layer in ("bass-mus", "orchestra-mus", "drums-mus"):  # a solo recording has no other layers
            if not (view / f"{layer}.mid").exists():
                import pretty_midi

                pretty_midi.PrettyMIDI().write(str(view / f"{layer}.mid"))
        # The footer on arranged parts is in the job's language when it has one (en otherwise).
        lang = ["--lang", ctx.params["lang"]] if ctx.params.get("lang") else []
        _python(ctx, "brasscribe_eval.arrange_layers_song", "--layers", str(view), "--beats", str(ctx.inputs["beats"]),
                "--out", str(ctx.out), "--title", ctx.params["title"], "--no-render", *lang,
                *_arrangement_flags(ctx, "brasscribe_eval.arrange_layers_song"))
    _stable_musicxml(ctx)


def arrange_band(ctx: StageContext) -> None:
    """Pipeline A/B: melody (MuScriptor, Basic Pitch support), bass line, harmony reduction (arrange_song)."""
    i = ctx.inputs
    harmony = [str(v) for k, v in sorted(i.items()) if k.startswith("harmony")]
    args = ["--beats", str(i["beats"]), "--melody", str(i["melody"]), "--bass", str(i["bass"]),
            "--harmony", *harmony, "--out", str(ctx.out), "--title", ctx.params["title"], "--no-render"]
    if "melody_support" in i:
        args[4:4] = ["--melody-support", str(i["melody_support"])]
    _python(ctx, "brasscribe_eval.arrange_song", *args, *_arrangement_flags(ctx, "brasscribe_eval.arrange_song"))
    _stable_musicxml(ctx)


def export(ctx: StageContext) -> None:
    """Score PDF, MIDI and (optionally) MP3, plus one PDF per part, via the MuseScore CLI.

    MuseScore 4 aborts during shutdown after writing its output, so success is
    judged by the output file, never the exit code.
    """
    score = ctx.inputs["score"]
    xml = score / "brass-band.musicxml"
    formats = ["pdf", "mid"] + (["mp3"] if ctx.params.get("audio", True) else [])
    from brasscribe_music import musescore

    mscore = musescore.binary()
    written = []
    if mscore:
        dsts = [ctx.out / f"brass-band.{ext}" for ext in formats]
        parts = sorted((score / "parts").glob("*.musicxml"))
        part_dsts = [ctx.out / "parts" / part.with_suffix(".pdf").name for part in parts]
        missing = musescore.convert_many([(xml, dsts)])
        missing += musescore.convert_many(list(zip(parts, part_dsts)),
                                          style=PART_STYLE if PART_STYLE.exists() else None)
        if missing:
            raise StageFailed(ctx.stage.name, f"MuseScore did not write {missing[0].name}")
        written = [d.name for d in dsts] + [f"parts/{d.name}" for d in part_dsts]
    if not mscore:
        ctx.log("mscore not found: PDF, MIDI and MP3 skipped")
    accessible = accessible_exports(score, ctx)
    written += accessible.pop("written")
    (ctx.out / "export.json").write_text(json.dumps({"musescore": mscore, "written": written,
                                                     "skipped": [] if mscore else formats, **accessible}, indent=1))


def accessible_exports(score: Path, ctx: StageContext) -> dict:
    """Braille music (BRF) for the score and every part, and the talking score (JSON, HTML, text).

    Neither needs MuseScore. A part music21 cannot transcribe is listed, not fatal."""
    from . import braille, talking_score

    written, failed, dropped = [], {}, []
    xml = score / "brass-band.musicxml"
    for src in [xml, *sorted((score / "parts").glob("*.musicxml"))]:
        rel = "brass-band.brf" if src == xml else f"parts/{src.with_suffix('.brf').name}"
        try:
            r = braille.translate(src)
        except Exception as e:  # noqa: BLE001 - reported per file
            failed[rel] = f"{type(e).__name__}: {e}"
            ctx.log(f"braille {rel} failed: {failed[rel]}")
            continue
        dst = ctx.out / rel
        dst.parent.mkdir(exist_ok=True)
        dst.write_bytes(r.brf.encode("ascii"))
        written.append(rel)
        if r.text_directions_dropped:
            dropped.append(rel)
    comp = talking_score.load_composition(score / "composition.json")
    doc = talking_score.build(xml, comp)
    (ctx.out / "talking-score.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    en = talking_score.Settings()
    (ctx.out / "talking-score.html").write_text(talking_score.to_html(doc, en))
    (ctx.out / "talking-score.txt").write_text(talking_score.to_text(doc, en))
    written += ["talking-score.json", "talking-score.html", "talking-score.txt"]
    return {"written": written, "braille_failed": failed, "braille_text_directions_dropped": dropped}
