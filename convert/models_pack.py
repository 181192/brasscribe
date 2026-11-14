"""Pack, pin, fetch and verify the on-device models the phone and Mac apps bundle (they are converted, not in git).

    python3 convert/models_pack.py fetch  [FILE...]        # download the pinned release, verify, install into models/converted
    python3 convert/models_pack.py verify [FILE...]        # models/converted matches the pin (exit 1 if not)
    python3 convert/models_pack.py pack   [--version TAG]  # after a conversion: write models/pack and rewrite the pin

convert/on-device-models.json pins one pack: the GitHub release tag (`version`) in this repository and the
size and sha256 of every file. A Core ML model is a folder (`.mlpackage`), so it travels as a `.zip` of that
folder, stored without compression and with fixed dates: the same folder always gives the same file, which is
how `verify` checks an installed folder against the pin. ONNX models travel as they are. Each file's `into`
is its folder under models/converted, the layout the apps' builds read (apps/apple/scripts/stage-models.sh,
apps/android/products/brasscribe/build.gradle.kts).

`fetch` uses the GitHub CLI (`gh release download`), which needs a login (`gh auth login`) or GH_TOKEN. What is
already in models/converted with the pinned content is kept; anything else is replaced by the pinned file. The
release's SHA256SUMS must agree with the pin, and every file must match it, or nothing is installed.

A release build that bundles the models fetches before it builds and stops when the files cannot be had, so it
never ships without them and quietly sends solos to the computer.

Publishing a new pack: convert the models (convert/README.md), `pack --version models-YYYY.MM.DD` (it also
puts NOTICE.md, each model's source and licence from convert/on-device-models-NOTICE.md, among the files), then
`gh release create models-YYYY.MM.DD --prerelease models/pack/*`, and commit the pin.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONVERTED = ROOT / "models" / "converted"
PACK = ROOT / "models" / "pack"
PIN = Path(__file__).resolve().parent / "on-device-models.json"
NOTICE = Path(__file__).resolve().parent / "on-device-models-NOTICE.md"  # each model's source and licence
SUMS = "SHA256SUMS"
ZIP = ".zip"
GH_TIMEOUT = 600  # seconds for one `gh release download`; a stalled one is tried once more


def load_pin() -> dict:
    return json.loads(PIN.read_text())


def selected(pin: dict, names: list[str]) -> dict[str, dict]:
    files = pin["files"]
    unknown = [n for n in names if n not in files]
    if unknown:
        raise SystemExit(f"not in {PIN.name}: {', '.join(unknown)} (pinned: {', '.join(files)})")
    return {n: files[n] for n in (names or files)}


def folder_zip(folder: Path) -> bytes:
    """The folder as a zip whose bytes depend only on the folder's files: sorted, stored, one fixed date."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(q for q in folder.rglob("*") if q.is_file() and q.name != ".DS_Store"):
            info = zipfile.ZipInfo(f"{folder.name}/{p.relative_to(folder).as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
    return out.getvalue()


def packed(name: str, want: dict, converted: Path) -> bytes | None:
    """What the pack file `name` would hold, made from what is installed (None when it is not there)."""
    src = converted / want["into"] / name.removesuffix(ZIP)
    if name.endswith(ZIP):
        return folder_zip(src) if src.is_dir() else None
    return src.read_bytes() if src.is_file() else None


def matches(data: bytes | None, want: dict) -> bool:
    return data is not None and len(data) == want["size"] and hashlib.sha256(data).hexdigest() == want["sha256"]


def parse_sums(text: str) -> dict[str, str]:
    """`<sha256>  <name>` lines (sha256sum / shasum -a 256 output, `*name` in binary mode too)."""
    out = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[1].strip().lstrip("*")] = parts[0].lower()
    return out


def verify(converted: Path, names: list[str]) -> int:
    bad = 0
    for n, v in selected(load_pin(), names).items():
        where = converted / v["into"] / n.removesuffix(ZIP)
        data = packed(n, v, converted)
        if data is None:
            print(f"missing {where}", file=sys.stderr)
            bad += 1
        elif not matches(data, v):
            print(f"differs from convert/{PIN.name}: {where}", file=sys.stderr)
            bad += 1
        else:
            print(f"ok {v['into']}/{n.removesuffix(ZIP)}")
    return 1 if bad else 0


def gh_download(pin: dict, patterns: list[str], into: Path) -> None:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit("the GitHub CLI (gh) is needed to fetch the models: https://cli.github.com, then `gh auth login`")
    cmd = [gh, "release", "download", pin["version"], "--repo", pin["repo"], "--dir", str(into), "--clobber"]
    for p in patterns:
        cmd += ["--pattern", p]
    for attempt in (1, 2):
        print(f"gh release download {pin['version']} ({', '.join(patterns)})", flush=True)
        try:
            if subprocess.run(cmd, timeout=GH_TIMEOUT).returncode == 0:
                return
            why = "failed"
        except subprocess.TimeoutExpired:
            why = f"took longer than {GH_TIMEOUT} s"
        print(f"the download {why}" + ("; trying once more" if attempt == 1 else ""), file=sys.stderr, flush=True)
    raise SystemExit(f"could not download the models from release {pin['version']} of {pin['repo']} "
                     "(logged in with `gh auth login`, or GH_TOKEN set with contents: read?)")


def umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def install(name: str, want: dict, data: bytes, converted: Path) -> None:
    """Put one checked file in place. The new file or folder is written beside the target inside its folder and
    then renamed over it, so an interrupted install leaves the old model or the new one, never half of either."""
    into = converted / want["into"]
    into.mkdir(parents=True, exist_ok=True)
    target = into / name.removesuffix(ZIP)
    if not name.endswith(ZIP):
        fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=into)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o666 & ~umask())  # mkstemp makes it 0600; give it what a plain write would
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            top = f"{target.name}/"
            if any(not m.startswith(top) or ".." in Path(m).parts for m in z.namelist()):
                raise SystemExit(f"{name} holds files outside {target.name}; nothing installed")
            staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=into))
            try:
                z.extractall(staging)
                old = None
                if target.exists():
                    old = staging / "old"
                    os.replace(target, old)
                try:
                    os.replace(staging / target.name, target)
                except BaseException:
                    if old is not None:
                        os.replace(old, target)
                    raise
            finally:
                shutil.rmtree(staging, ignore_errors=True)
    print(f"installed {target}")


def leftovers(converted: Path, want: dict[str, dict]) -> None:
    """Remove what an install that was killed left beside its target (the `.<name>.*` staging files and folders)."""
    for n, v in want.items():
        into = converted / v["into"]
        for p in into.glob(f".{n.removesuffix(ZIP)}.*") if into.is_dir() else ():
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)


def fetch(converted: Path, names: list[str]) -> int:
    pin = load_pin()
    want = selected(pin, names)
    leftovers(converted, want)
    todo = [n for n, v in want.items() if not matches(packed(n, v, converted), v)]
    for n in want:
        if n not in todo:
            print(f"ok {n.removesuffix(ZIP)} (already here)")
    if todo:
        with tempfile.TemporaryDirectory(prefix="models-fetch-") as tmp:
            t = Path(tmp)
            gh_download(pin, [SUMS, *todo], t)
            sums = parse_sums((t / SUMS).read_text())
            got = {}
            for n in todo:
                if sums.get(n) != want[n]["sha256"]:
                    raise SystemExit(f"{SUMS} of {pin['version']} says {sums.get(n)} for {n}, the pin says {want[n]['sha256']}")
                got[n] = (t / n).read_bytes() if (t / n).is_file() else None
                if not matches(got[n], want[n]):
                    raise SystemExit(f"{n} from {pin['version']} does not match its sha256/size; nothing installed")
            for n in todo:
                install(n, want[n], got[n], converted)
    return verify(converted, list(want))


def pack(version: str | None, converted: Path, out: Path) -> int:
    pin = load_pin()
    if version:
        pin["version"] = version
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for n, v in pin["files"].items():
        data = packed(n, v, converted)
        if data is None:
            raise SystemExit(f"missing {converted / v['into'] / n.removesuffix(ZIP)} (convert/README.md)")
        (out / n).write_bytes(data)
        v.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    (out / SUMS).write_text("".join(f"{v['sha256']}  {n}\n" for n, v in pin["files"].items()))
    shutil.copyfile(NOTICE, out / "NOTICE.md")
    PIN.write_text(json.dumps(pin, indent=1) + "\n")
    print(f"{PIN} ({pin['version']}), files in {out}: "
          + ", ".join(f"{n} {v['size'] / 1e6:.1f} MB" for n, v in pin["files"].items()))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--dir", type=Path, default=CONVERTED, help="where the models are installed (default: models/converted)")
        s.add_argument("files", nargs="*", help="pinned file names (default: all)")
    p = sub.add_parser("pack")
    p.add_argument("--version", help="release tag of the new pack, e.g. models-2026.11.13")
    p.add_argument("--dir", type=Path, default=CONVERTED, help="where the converted models are (default: models/converted)")
    p.add_argument("--out", type=Path, default=PACK, help="where the pack's files are written (default: models/pack)")
    a = ap.parse_args(argv)
    if a.cmd == "pack":
        return pack(a.version, a.dir.resolve(), a.out.resolve())
    return (fetch if a.cmd == "fetch" else verify)(a.dir.resolve(), a.files)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
