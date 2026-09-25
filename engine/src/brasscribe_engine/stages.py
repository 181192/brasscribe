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
SYMBOLIC_CODE = (MUSIC_SRC, EVAL_SRC, THIS)


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
        (where / name).symlink_to(src.resolve())
    return where


def _stable_musicxml(ctx: StageContext) -> None:
    """Deterministic part/instrument ids, so an unchanged arrangement has unchanged bytes (and downstream cache hits)."""
    from .compare import stable_ids

    xml = ctx.out / "brass-band.musicxml"
    if xml.exists():
        xml.write_text(stable_ids(xml.read_text()))


def arrange_layered(ctx: StageContext) -> None:
    names = {k: v for k, v in ctx.inputs.items() if k.endswith((".mid", ".npz"))}
    with tempfile.TemporaryDirectory(dir=ctx.out.parent) as tmp:
        view = _view(names, Path(tmp) / "layers")
        _python(ctx, "brasscribe_eval.arrange_layers_song", "--layers", str(view), "--beats", str(ctx.inputs["beats"]),
                "--out", str(ctx.out), "--title", ctx.params["title"], "--no-render")
    _stable_musicxml(ctx)


def arrange_band(ctx: StageContext) -> None:
    """Pipeline A/B: melody (MuScriptor, Basic Pitch support), bass line, harmony reduction (arrange_song)."""
    i = ctx.inputs
    harmony = [str(v) for k, v in sorted(i.items()) if k.startswith("harmony")]
    args = ["--beats", str(i["beats"]), "--melody", str(i["melody"]), "--bass", str(i["bass"]),
            "--harmony", *harmony, "--out", str(ctx.out), "--title", ctx.params["title"], "--no-render"]
    if "melody_support" in i:
        args[4:4] = ["--melody-support", str(i["melody_support"])]
    _python(ctx, "brasscribe_eval.arrange_song", *args)
    _stable_musicxml(ctx)


def arrange_solo(ctx: StageContext) -> None:
    i = ctx.inputs
    _python(ctx, "brasscribe_eval.arrange_solo", "--beats", str(i["beats"]), "--sw", str(i["sw"]), "--mus", str(i["mus"]),
            "--bp", str(i["bp"]), "--out", str(ctx.out), "--title", ctx.params["title"])
    _stable_musicxml(ctx)


def export(ctx: StageContext) -> None:
    """PDF, MIDI and (optionally) MP3 via the MuseScore CLI.

    MuseScore 4 aborts during shutdown after writing its output, so success is
    judged by the output file, never the exit code.
    """
    xml = ctx.inputs["musicxml"]
    formats = ["pdf", "mid"] + (["mp3"] if ctx.params.get("audio", True) else [])
    mscore = shutil.which("mscore")
    written = []
    for ext in formats if mscore else []:
        dst = ctx.out / f"brass-band.{ext}"
        subprocess.run([mscore, "-o", str(dst), str(xml)], capture_output=True)
        if not dst.exists():
            raise StageFailed(ctx.stage.name, f"MuseScore did not write {dst.name}")
        written.append(dst.name)
    if not mscore:
        ctx.log("mscore not found: PDF, MIDI and MP3 skipped")
    (ctx.out / "export.json").write_text(json.dumps({"musescore": mscore, "written": written,
                                                     "skipped": [] if mscore else formats}, indent=1))
