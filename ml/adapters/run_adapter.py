"""Cross-platform adapter runner (stdlib only): `python run_adapter.py <adapter> <input> <output>`.

Each adapter's run.sh delegates here, and the engine calls this file directly,
so the same invocation works on macOS, Linux and Windows. The command runs in
the adapter's environment:

  BRASSCRIBE_ADAPTER_RUNNER=uv    the uv project in ml/adapters/<adapter> (default on macOS on Apple
                                  silicon, the only platform the uv lock files are solved for)
  BRASSCRIBE_ADAPTER_RUNNER=pixi  the pixi environment <adapter> of the repo's pixi.toml (default elsewhere);
                                  BRASSCRIBE_CUDA=1 picks <adapter>-cuda for torch adapters

Outputs appear whole or not at all: each is written next to its destination and renamed into place.

Adapters and their output:
  basic-pitch       <input.wav> <output.mid>     (BASIC_PITCH_SERIALIZATION; ONNX outside macOS)
  beat-this         <input.wav> <output.beats>     (BEAT_THIS_MODEL, default final0)
  mega53            <input audio> <output dir>   (<stem>.flac for all 53 stems)
  muscriptor        <input.wav> <output.mid>     (MUSCRIPTOR_MODEL, MUSCRIPTOR_INSTRUMENTS)
  separator         <input.wav> <output dir>     (SEPARATOR_MODEL)
  swift-f0          <input.wav> <output.mid>     (monophonic lines)
  swift-f0-contour  <input.wav> <output.npz>     (frame-level SwiftF0 contour)
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODELS = Path(os.environ.get("BRASSCRIBE_MODELS") or ROOT / "models")
TORCH = {"beat-this", "mega53", "muscriptor", "separator"}
MSST_REPO = "https://github.com/ZFTurbo/Music-Source-Separation-Training"
MSST_REV = "050cae7"
MEGA53_RELEASE = f"{MSST_REPO}/releases/download/v1.0.21"
# name -> (size in bytes, SHA-256) of the v1.0.21 release assets
MEGA53_FILES = {
    "mvsep_mega_model_bs_roformer_53_stems.yaml":
        (4_184, "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"),
    "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt":
        (1_368_919_887, "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"),
}
MEGA53_CONFIG, MEGA53_CKPT = MEGA53_FILES
MEGA53_STEMS = 53
STDERR_TAIL = 4000  # characters of a failed model's stderr to pass on


def runner() -> str:
    """The uv projects are locked for macOS on Apple silicon only; anywhere else pixi is the default."""
    default = "uv" if sys.platform == "darwin" and platform.machine() == "arm64" else "pixi"
    return os.environ.get("BRASSCRIBE_ADAPTER_RUNNER") or default


def cuda() -> bool:
    return os.environ.get("BRASSCRIBE_CUDA", "").strip().lower() not in ("", "0", "false", "no", "off")


def env_cmd(project: str, cmd: list[str]) -> list[str]:
    """Wrap cmd so it runs in the environment of adapter project `project`."""
    if runner() == "pixi":
        env = project + ("-cuda" if project in TORCH and cuda() else "")
        return ["pixi", "run", "--manifest-path", str(ROOT / "pixi.toml"), "--frozen", "-e", env, *cmd]
    return ["uv", "run", "--frozen", "--project", str(HERE / project), *cmd]


def run(project: str, cmd: list[str], quiet_stderr: bool = True) -> None:
    """Run cmd in the adapter's environment. Its stderr is kept back unless it fails; then its tail is shown."""
    proc = subprocess.run(env_cmd(project, cmd), stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE if quiet_stderr else None, text=True, errors="replace")
    if proc.returncode != 0:
        if proc.stderr:
            sys.stderr.write(proc.stderr[-STDERR_TAIL:])
        raise subprocess.CalledProcessError(proc.returncode, proc.args)


@contextmanager
def atomic(dst: Path) -> Iterator[Path]:
    """A path next to dst (same suffix: tools pick the format from it) that becomes dst when the block succeeds."""
    part = dst.with_name(f"{dst.stem}.part{dst.suffix}")
    part.unlink(missing_ok=True)
    try:
        yield part
        os.replace(part, dst)
    finally:
        part.unlink(missing_ok=True)


@contextmanager
def staging(dst: Path) -> Iterator[Path]:
    """A directory inside dst for files that are moved into dst, one rename each, when the block succeeds."""
    dst.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dst, prefix=".partial-") as tmp:
        yield Path(tmp)
        for f in sorted(Path(tmp).iterdir()):
            if f.is_file():
                os.replace(f, dst / f.name)


SNDFILE_SUFFIXES = {".wav", ".flac", ".aif", ".aiff", ".ogg"}


def readable(src: Path, tmp: str) -> Path:
    """src itself if libsndfile reads it, else a WAV decoded by ffmpeg at the source rate and channels."""
    if src.suffix.lower() in SNDFILE_SUFFIXES:
        return src
    audio = Path(tmp) / f"{src.stem}.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vn", str(audio)], check=True)
    return audio


def basic_pitch(src: Path, dst: Path) -> None:
    # macOS keeps Basic Pitch's own choice (CoreML). Elsewhere it would pick the TFLite model,
    # which the environment's TFLite runtime cannot load, so ask for ONNX explicitly.
    serial = os.environ.get("BASIC_PITCH_SERIALIZATION") or (None if sys.platform == "darwin" else "onnx")
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as dec:
        src = readable(src, dec)
        run("basic-pitch", ["basic-pitch", tmp, str(src), *(["--model-serialization", serial] if serial else [])])
        mids = list(Path(tmp).glob("*.mid"))
        if not mids:
            raise SystemExit("basic-pitch wrote no MIDI")
        with atomic(dst) as part:
            shutil.move(str(mids[0]), part)


def beat_this(src: Path, dst: Path) -> None:
    model = os.environ.get("BEAT_THIS_MODEL")  # e.g. small0, the model the Play apps run on device
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "input.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
                        str(audio)], check=True)
        with atomic(dst) as part:
            run("beat-this", ["beat_this", str(audio), "-o", str(part), *(["--model", model] if model else [])])


def muscriptor(src: Path, dst: Path) -> None:
    # MuScriptor downmixes and resamples to 16 kHz itself. Its greedy decoding changes with the resampler,
    # so it gets the original samples (the committed eval fixtures were made that way); ffmpeg only
    # decodes what libsndfile cannot read.
    with tempfile.TemporaryDirectory() as tmp:
        audio = readable(src, tmp)
        with atomic(dst) as part:
            cmd = ["muscriptor", "transcribe", str(audio), "-m", os.environ.get("MUSCRIPTOR_MODEL", "medium"),
                   "-o", str(part), "--detect-tempo", "false"]
            if os.environ.get("MUSCRIPTOR_INSTRUMENTS"):
                cmd += ["--instruments", os.environ["MUSCRIPTOR_INSTRUMENTS"]]
            run("muscriptor", cmd)


def separator(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp, staging(dst) as out:
        run("separator", ["audio-separator", str(readable(src, tmp)), "-m",
                          os.environ.get("SEPARATOR_MODEL", "BS-Roformer-SW.ckpt"), "--output_dir", str(out),
                          "--output_format", "WAV", "--model_file_dir", str(MODELS / "separator")])


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mega53_setup() -> None:
    """Pinned MSST inference code and Mega-53 v1 weights (licence unstated; personal use). Idempotent: fetches
    only what is missing, and a weights file of the wrong size (an interrupted download) again."""
    msst = HERE / "mega53" / "msst"
    if not msst.is_dir():
        # Cloned beside it and renamed, so an interrupted clone leaves no msst/ behind to be taken as complete.
        with tempfile.TemporaryDirectory(dir=msst.parent, prefix=".msst-") as tmp:
            clone = Path(tmp) / "msst"
            subprocess.run(["git", "clone", "-q", MSST_REPO, str(clone)], check=True)
            subprocess.run(["git", "-C", str(clone), "checkout", "-q", MSST_REV], check=True)
            os.replace(clone, msst)
    elif (msst / ".git").exists():
        subprocess.run(["git", "-C", str(msst), "checkout", "-q", MSST_REV], check=True)
    # (The apps ship msst/ without .git, already at MSST_REV.)
    models = MODELS / "mega53"
    models.mkdir(parents=True, exist_ok=True)
    for name, (size, sha256) in MEGA53_FILES.items():
        target = models / name
        if target.is_file() and target.stat().st_size == size:
            continue
        with atomic(target) as part:
            urllib.request.urlretrieve(f"{MEGA53_RELEASE}/{name}", part)
            got = _sha256(part)
            if got != sha256:
                raise SystemExit(f"{name}: SHA-256 {got}, expected {sha256}; not kept")


def mega53(src: Path, dst: Path) -> None:
    mega53_setup()
    models = MODELS / "mega53"
    with tempfile.TemporaryDirectory() as tmp:
        name = src.stem
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
                        str(Path(tmp) / f"{name}.wav")], check=True)
        (Path(tmp) / "out").mkdir()
        run("mega53", ["python", str(HERE / "mega53" / "msst" / "inference.py"), "--model_type", "bs_roformer",
                       "--config_path", str(models / MEGA53_CONFIG), "--start_check_point", str(models / MEGA53_CKPT),
                       "--input_folder", tmp, "--store_dir", str(Path(tmp) / "out"), "--disable_detailed_pbar",
                       "--pcm_type", "PCM_16"])
        # MSST writes a stem that peaks above full scale as WAV instead of FLAC (16-bit, clipped all the same).
        stems = Path(tmp) / "out" / name
        for f in sorted(stems.glob("*.wav")):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(f), str(f.with_suffix(".flac"))], check=True)
            f.unlink()
        flacs = sorted(stems.glob("*.flac"))
        if len(flacs) < MEGA53_STEMS:
            raise SystemExit(f"mega53 wrote {len(flacs)} of {MEGA53_STEMS} stems for {src.name}")
        with staging(dst) as out:
            for f in flacs:
                shutil.move(str(f), out / f.name)


def swift_f0(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with atomic(dst) as part:
            run("swift-f0", ["python", str(HERE / "swift-f0" / "transcribe.py"), str(readable(src, tmp)), str(part)],
                quiet_stderr=False)


def swift_f0_contour(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with atomic(dst) as part:
            run("swift-f0", ["python", str(HERE / "swift-f0" / "contour.py"), str(readable(src, tmp)), str(part)],
                quiet_stderr=False)


ADAPTERS = {"basic-pitch": basic_pitch, "beat-this": beat_this, "mega53": mega53, "muscriptor": muscriptor,
            "separator": separator, "swift-f0": swift_f0, "swift-f0-contour": swift_f0_contour}


def main(argv: list[str]) -> int:
    if argv == ["--setup", "mega53"]:  # ml/adapters/mega53/setup.sh
        mega53_setup()
        return 0
    if len(argv) != 3 or argv[0] not in ADAPTERS:
        print(f"usage: run_adapter.py {{{','.join(ADAPTERS)}}} <input> <output>", file=sys.stderr)
        return 2
    name, src, dst = argv[0], Path(argv[1]).resolve(), Path(argv[2]).resolve()
    ADAPTERS[name](src, dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
