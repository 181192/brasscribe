"""Cross-platform adapter runner (stdlib only): `python run_adapter.py <adapter> <input> <output>`.

Each adapter's run.sh delegates here, and the engine calls this file directly,
so the same invocation works on macOS, Linux and Windows. The command runs in
the adapter's environment:

  BRASSCRIBE_ADAPTER_RUNNER=uv    (default) the uv project in ml/adapters/<adapter>
  BRASSCRIBE_ADAPTER_RUNNER=pixi  the pixi environment <adapter> of the repo's pixi.toml;
                                  BRASSCRIBE_CUDA=1 picks <adapter>-cuda for torch adapters

Adapters and their output:
  basic-pitch       <input.wav> <output.mid>
  beat-this         <input.wav> <output.beats>
  mega53            <input audio> <output dir>   (<stem>.flac for all 53 stems)
  muscriptor        <input.wav> <output.mid>     (MUSCRIPTOR_MODEL, MUSCRIPTOR_INSTRUMENTS)
  separator         <input.wav> <output dir>     (SEPARATOR_MODEL)
  swift-f0          <input.wav> <output.mid>     (monophonic lines)
  swift-f0-contour  <input.wav> <output.npz>     (frame-level SwiftF0 contour)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODELS = Path(os.environ.get("BRASSCRIBE_MODELS") or ROOT / "models")
TORCH = {"beat-this", "mega53", "muscriptor", "separator"}
MSST_REPO = "https://github.com/ZFTurbo/Music-Source-Separation-Training"
MSST_REV = "050cae7"
MEGA53_RELEASE = f"{MSST_REPO}/releases/download/v1.0.21"
MEGA53_FILES = ("mvsep_mega_model_bs_roformer_53_stems.yaml", "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt")


def env_cmd(project: str, cmd: list[str]) -> list[str]:
    """Wrap cmd so it runs in the environment of adapter project `project`."""
    if os.environ.get("BRASSCRIBE_ADAPTER_RUNNER", "uv") == "pixi":
        env = project + ("-cuda" if project in TORCH and os.environ.get("BRASSCRIBE_CUDA") else "")
        return ["pixi", "run", "--manifest-path", str(ROOT / "pixi.toml"), "--frozen", "-e", env, *cmd]
    return ["uv", "run", "--project", str(HERE / project), *cmd]


def run(project: str, cmd: list[str], quiet_stderr: bool = True) -> None:
    subprocess.run(env_cmd(project, cmd), check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL if quiet_stderr else None)


def basic_pitch(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run("basic-pitch", ["basic-pitch", tmp, str(src)])
        mids = list(Path(tmp).glob("*.mid"))
        if not mids:
            raise SystemExit("basic-pitch wrote no MIDI")
        shutil.move(str(mids[0]), dst)


def beat_this(src: Path, dst: Path) -> None:
    run("beat-this", ["beat_this", str(src), "-o", str(dst)])


def muscriptor(src: Path, dst: Path) -> None:
    cmd = ["muscriptor", "transcribe", str(src), "-m", os.environ.get("MUSCRIPTOR_MODEL", "medium"), "-o", str(dst),
           "--detect-tempo", "false"]
    if os.environ.get("MUSCRIPTOR_INSTRUMENTS"):
        cmd += ["--instruments", os.environ["MUSCRIPTOR_INSTRUMENTS"]]
    run("muscriptor", cmd)


def separator(src: Path, dst: Path) -> None:
    run("separator", ["audio-separator", str(src), "-m", os.environ.get("SEPARATOR_MODEL", "BS-Roformer-SW.ckpt"),
                      "--output_dir", str(dst), "--output_format", "WAV", "--model_file_dir", str(MODELS / "separator")])


def mega53_setup() -> None:
    """Pinned MSST inference code and Mega-53 v1 weights (licence unstated; personal use)."""
    msst = HERE / "mega53" / "msst"
    if not msst.is_dir():
        subprocess.run(["git", "clone", "-q", MSST_REPO, str(msst)], check=True)
    subprocess.run(["git", "-C", str(msst), "checkout", "-q", MSST_REV], check=True)
    (MODELS / "mega53").mkdir(parents=True, exist_ok=True)
    for f in MEGA53_FILES:
        target = MODELS / "mega53" / f
        if not target.exists():
            urllib.request.urlretrieve(f"{MEGA53_RELEASE}/{f}", target)


def mega53(src: Path, dst: Path) -> None:
    if not (HERE / "mega53" / "msst").is_dir():
        mega53_setup()
    models = MODELS / "mega53"
    with tempfile.TemporaryDirectory() as tmp:
        name = src.stem
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
                        str(Path(tmp) / f"{name}.wav")], check=True)
        (Path(tmp) / "out").mkdir()
        run("mega53", ["python", str(HERE / "mega53" / "msst" / "inference.py"), "--model_type", "bs_roformer",
                       "--config_path", str(models / MEGA53_FILES[0]), "--start_check_point", str(models / MEGA53_FILES[1]),
                       "--input_folder", tmp, "--store_dir", str(Path(tmp) / "out"), "--disable_detailed_pbar",
                       "--pcm_type", "PCM_16"])
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted((Path(tmp) / "out" / name).glob("*.flac")):
            shutil.move(str(f), dst / f.name)


def swift_f0(src: Path, dst: Path) -> None:
    run("swift-f0", ["python", str(HERE / "swift-f0" / "transcribe.py"), str(src), str(dst)], quiet_stderr=False)


def swift_f0_contour(src: Path, dst: Path) -> None:
    run("swift-f0", ["python", str(HERE / "swift-f0" / "contour.py"), str(src), str(dst)], quiet_stderr=False)


ADAPTERS = {"basic-pitch": basic_pitch, "beat-this": beat_this, "mega53": mega53, "muscriptor": muscriptor,
            "separator": separator, "swift-f0": swift_f0, "swift-f0-contour": swift_f0_contour}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ADAPTERS:
        print(f"usage: run_adapter.py {{{','.join(ADAPTERS)}}} <input> <output>", file=sys.stderr)
        return 2
    name, src, dst = argv[0], Path(argv[1]).resolve(), Path(argv[2]).resolve()
    ADAPTERS[name](src, dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
