#!/usr/bin/env python3
"""List the on-device models inside release artifacts and fail when an app's set is wrong.

    .github/scripts/release-models.py dist/                      # every file in a folder
    .github/scripts/release-models.py path/to/app.apk other.ipa  # or the files themselves
    .github/scripts/release-models.py --require 'brasscribe-play-android-*.apk' dist/   # and that one is there

Prints a Markdown table with a row for every file: the models found in it and whether that is what the app must
carry (also into $GITHUB_STEP_SUMMARY when set). Exit 1 when an enforced rule fails, when an APK or IPA has no rule
(a file this script does not know cannot be vouched for), or when no file matches a --require pattern. The expected files and their sha256 and size
come from the pin, convert/on-device-models.json; RULES below says which pinned files go into which artifact and
where. ONNX files are bundled as they are, so their bytes are checked against the pin; Core ML packages are
compiled into .mlmodelc folders by the build, so only that the compiled weights are there and not empty. NOTICE.md
must be convert/on-device-models-NOTICE.md, byte for byte.
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
NOTICE = PIN.with_name("on-device-models-NOTICE.md")
UNKNOWN_FAILS = (".apk", ".ipa")  # an app package with no rule fails
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


ANDROID = ("swift-f0-window.onnx", "nmp-b1.onnx", "beat-this-small0.onnx")
APPLE = ("swift-f0-window-fp32.mlpackage.zip", "nmp-b1-fp32.mlpackage.zip", "beat-this-small0-fp16.mlpackage.zip")

# First match wins. brasscribe-*.apk also matches the unsigned APKs Gradle writes (brasscribe-<abi>-release-unsigned.apk).
RULES = (
    Rule("brasscribe-*.apk", "Play for Android", "assets/models/", onnx=ANDROID, notice=True),
    Rule("fretscribe-*.apk", "Fretscribe for Android", none=".onnx"),
    # The Apple apps do not bundle the models yet: these rules report, without failing, until their build does.
    Rule("brasscribe-play-ios*.ipa", "Play for iPhone and iPad", "Payload/BrasscribePlay.app/Models/",
         coreml=APPLE, notice=True, enforced=False),
    Rule("brasscribe-play-macos*.zip", "Play for Mac", "Brasscribe Play.app/Contents/Resources/Models/",
         coreml=APPLE, notice=True, enforced=False),
    Rule("fretscribe-ios*.ipa", "Fretscribe for iPhone and iPad", none=".mlmodelc", enforced=False),
    Rule("fretscribe-macos*.zip", "Fretscribe for Mac", none=".mlmodelc", enforced=False),
    # Play for Windows listens on the computer's engine only: no model in its download.
    Rule("brasscribe-play-windows*.zip", "Play for Windows", none=".onnx"),
)


def row(*cells: str) -> str:
    return "|" + "|".join(f" {c} " if c else " " for c in cells) + "|"


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


def check(path: Path, rule: Rule, pin: dict, notice_text: bytes) -> tuple[list[str], list[str]]:
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
            if notice not in infos:
                wrong.append(f"no {notice}")
            elif z.read(notice) != notice_text:
                wrong.append(f"{notice} is not convert/{NOTICE.name}")
            else:
                shown.append("NOTICE.md")
        if rule.none:
            wrong += [f"{m} should not be there" for m in found if m.endswith(rule.none)]
        if not (rule.onnx or rule.coreml):
            shown = found
    return shown, wrong


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path, help="artifacts, or folders of them")
    ap.add_argument("--pin", type=Path, default=PIN, help="the pin (default: convert/on-device-models.json)")
    ap.add_argument("--notice", type=Path, default=NOTICE, help="the models' notice (default: convert/on-device-models-NOTICE.md)")
    ap.add_argument("--require", action="append", default=[], metavar="GLOB",
                    help="fail unless a file's name matches GLOB (repeatable), e.g. 'brasscribe-play-android-*.apk'")
    a = ap.parse_args(argv)
    pin = json.loads(a.pin.read_text())
    notice_text = a.notice.read_bytes()
    unpinned = sorted({n for r in RULES for n in r.onnx + r.coreml} - set(pin["files"]))
    if unpinned:
        raise SystemExit(f"RULES names files that {a.pin.name} does not pin: {', '.join(unpinned)}")

    files = sorted(p for x in a.paths for p in (sorted(x.iterdir()) if x.is_dir() else [x]) if p.is_file())
    rows, problems = ["| file | app | models inside | result |", "|---|---|---|---|"], []
    for f in files:
        rule = rule_for(f.name)
        app = rule.app if rule else ""
        enforced = rule is not None and rule.enforced
        if rule is None and f.suffix in UNKNOWN_FAILS:
            rows.append(row(f"`{f.name}`", "", "", "**wrong**: no rule for this app package"))
            problems.append(f"{f.name}: no rule says which models it must carry (RULES in {Path(__file__).name})")
            continue
        if not zipfile.is_zipfile(f):
            if enforced:
                rows.append(row(f"`{f.name}`", app, "", "**wrong**: not a zip archive"))
                problems.append(f"{f.name}: not a zip archive")
            else:
                rows.append(row(f"`{f.name}`", app, "", "not a zip archive, not checked"))
            continue
        if rule is None:
            with zipfile.ZipFile(f) as z:
                found = models_in(z.namelist())
            rows.append(row(f"`{f.name}`", "", ", ".join(found) or "none", "no rule"))
            continue
        shown, wrong = check(f, rule, pin, notice_text)
        if not wrong:
            result = "ok"
        elif rule.enforced:
            result = "**wrong**: " + "; ".join(wrong)
            problems += [f"{f.name}: {w}" for w in wrong]
        else:
            result = "not enforced yet: " + "; ".join(wrong)
            for w in wrong:
                print(f"{f.name}: {w} (not enforced yet)", file=sys.stderr)
        rows.append(row(f"`{f.name}`", rule.app, ", ".join(shown) or "none", result))
    for glob in a.require:
        if not any(fnmatch.fnmatchcase(f.name, glob) for f in files):
            rows.append(row(f"`{glob}`", getattr(rule_for(glob.replace("*", "x")), "app", ""), "", "**wrong**: no such file"))
            problems.append(f"no file matches {glob}, which is required")
    for problem in problems:
        print(problem, file=sys.stderr)
    failed = bool(problems)
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
