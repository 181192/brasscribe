#!/usr/bin/env python3
"""List the on-device models inside release artifacts and fail when an app's set is wrong.

    .github/scripts/release-models.py dist/                      # every file in a folder
    .github/scripts/release-models.py path/to/app.apk other.ipa  # or the files themselves

Prints a Markdown table: per file, the models found in it and whether that is what the app must carry (also into
$GITHUB_STEP_SUMMARY when set). Exit 1 when an enforced rule fails. The expected files and their sha256 and size
come from the pin, convert/on-device-models.json; RULES below says which pinned files go into which artifact and
where. ONNX files are bundled as they are, so their bytes are checked against the pin; Core ML packages are
compiled into .mlmodelc folders by the build, so only that the compiled weights are there and not empty.
Standard library only; an APK, an IPA and the Mac zip are all zip files.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

PIN = Path(__file__).resolve().parents[2] / "convert" / "on-device-models.json"
MODEL_SUFFIXES = (".onnx", ".mlmodelc", ".mlpackage", ".tflite")


@dataclass(frozen=True)
class Rule:
    pattern: str  # file name glob
    app: str
    folder: str = ""  # where the models are inside the artifact
    onnx: tuple[str, ...] = ()  # pinned .onnx files that must be in `folder`, byte for byte
    coreml: tuple[str, ...] = ()  # pinned .mlpackage.zip files whose compiled .mlmodelc must be in `folder`
    notice: bool = False  # `folder`/NOTICE.md (convert/on-device-models-NOTICE.md) must be there
    none: str = ""  # no model of this suffix anywhere ("" = no such rule)
    enforced: bool = True  # False: report only (the build does not bundle them yet)
    check: bool = True  # False: list what is there, no rule


ANDROID = ("swift-f0-window.onnx", "nmp-b1.onnx", "beat-this-small0.onnx")
APPLE = ("swift-f0-window-fp32.mlpackage.zip", "nmp-b1-fp32.mlpackage.zip", "beat-this-small0-fp16.mlpackage.zip")

# First match wins. brasscribe-*.apk also matches the unsigned APKs Gradle writes (brasscribe-<abi>-release-unsigned.apk).
RULES = (
    Rule("brasscribe-*.apk", "Play for Android", "assets/models/", onnx=ANDROID, notice=True),
    Rule("fretscribe-*.apk", "Fretscribe for Android", none=".onnx"),
    # The Apple apps bundle the models once their build stages them (apps/apple/scripts/stage-models.sh).
    Rule("brasscribe-play-ios*.ipa", "Play for iPhone and iPad", "Payload/BrasscribePlay.app/Models/",
         coreml=APPLE, notice=True, enforced=False),
    Rule("brasscribe-play-macos*.zip", "Play for Mac", "Brasscribe Play.app/Contents/Resources/Models/",
         coreml=APPLE, notice=True, enforced=False),
    Rule("fretscribe-ios*.ipa", "Fretscribe for iPhone and iPad", none=".mlmodelc", enforced=False),
    Rule("fretscribe-macos*.zip", "Fretscribe for Mac", none=".mlmodelc", enforced=False),
    # Windows takes SwiftF0 from models/converted when it is there (Kalli.Brasscribe.csproj); not a rule yet.
    Rule("brasscribe-play-windows*.zip", "Play for Windows", check=False),
)


def rule_for(name: str) -> Rule | None:
    return next((r for r in RULES if fnmatch.fnmatchcase(name, r.pattern)), None)


def models_in(names: list[str]) -> list[str]:
    """Every model in the archive, by its path: files ending in a model suffix, and folders (.mlmodelc) once."""
    found = []
    for n in names:
        if n.startswith("__MACOSX/"):
            continue
        parts = n.rstrip("/").split("/")
        for i, part in enumerate(parts):
            if part.endswith(MODEL_SUFFIXES):
                path = "/".join(parts[: i + 1])
                if path not in found:
                    found.append(path)
                break
    return found


def check(path: Path, rule: Rule, pin: dict) -> tuple[list[str], list[str]]:
    """(what is there, what is wrong) for one artifact."""
    with zipfile.ZipFile(path) as z:
        infos = {i.filename: i for i in z.infolist()}
        found = models_in(list(infos))
        shown, wrong = [], []
        for name in rule.onnx:
            want = pin["files"][name]
            entry = rule.folder + name
            if entry not in infos:
                wrong.append(f"no {entry}")
                continue
            data = z.read(entry)
            if len(data) != want["size"] or hashlib.sha256(data).hexdigest() != want["sha256"]:
                wrong.append(f"{entry} is not the pinned file ({len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:12]}…)")
            else:
                shown.append(f"{name} (sha256 {want['sha256'][:12]}… ok)")
        for name in rule.coreml:
            compiled = name.removesuffix(".mlpackage.zip") + ".mlmodelc"
            weights = f"{rule.folder}{compiled}/weights/weight.bin"
            if weights not in infos or infos[weights].file_size == 0:
                wrong.append(f"no {weights}" if weights not in infos else f"{weights} is empty")
            else:
                shown.append(f"{compiled} ({infos[weights].file_size / 1e6:.1f} MB weights)")
        if rule.onnx or rule.coreml:
            expected = {rule.folder + n for n in rule.onnx} | {
                rule.folder + n.removesuffix(".mlpackage.zip") + ".mlmodelc" for n in rule.coreml}
            wrong += [f"{m} should not be there" for m in found if m not in expected]
        if rule.notice:
            notice = rule.folder + "NOTICE.md"
            if notice in infos and infos[notice].file_size > 0:
                shown.append("NOTICE.md")
            else:
                wrong.append(f"no {notice}")
        if rule.none:
            wrong += [f"{m} should not be there" for m in found if m.endswith(rule.none)]
        if not (rule.onnx or rule.coreml):
            shown = found
    return shown, wrong


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path, help="artifacts, or folders of them")
    ap.add_argument("--pin", type=Path, default=PIN, help="the pin (default: convert/on-device-models.json)")
    a = ap.parse_args(argv)
    pin = json.loads(a.pin.read_text())
    unpinned = sorted({n for r in RULES for n in r.onnx + r.coreml} - set(pin["files"]))
    if unpinned:
        raise SystemExit(f"RULES names files that {a.pin.name} does not pin: {', '.join(unpinned)}")

    files = sorted(p for x in a.paths for p in (sorted(x.iterdir()) if x.is_dir() else [x]) if p.is_file())
    rows, failed = ["| file | app | models inside | result |", "|---|---|---|---|"], False
    for f in files:
        rule = rule_for(f.name)
        if not zipfile.is_zipfile(f):
            if rule is not None and rule.check and rule.enforced:
                rows.append(f"| `{f.name}` | {rule.app} | | **wrong**: not a zip archive |")
                print(f"{f.name}: not a zip archive", file=sys.stderr)
                failed = True
            continue
        if rule is None:
            with zipfile.ZipFile(f) as z:
                found = models_in(z.namelist())
            rows.append(f"| `{f.name}` | | {', '.join(found) or 'none'} | no rule |")
            continue
        shown, wrong = check(f, rule, pin)
        if not rule.check:
            result = "listed only"
        elif not wrong:
            result = "ok"
        elif rule.enforced:
            result, failed = "**wrong**: " + "; ".join(wrong), True
        else:
            result = "not enforced yet: " + "; ".join(wrong)
        rows.append(f"| `{f.name}` | {rule.app} | {', '.join(shown) or 'none'} | {result} |")
        for w in wrong if rule.check else ():
            print(f"{f.name}: {w}{'' if rule.enforced else ' (not enforced yet)'}", file=sys.stderr)
    table = "\n".join(rows) + "\n"
    print(table, end="")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as s:
            s.write("### On-device models in the release files\n\n" + table + "\n")
    if failed:
        print("a release file does not carry the on-device models its app needs (see above)", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
