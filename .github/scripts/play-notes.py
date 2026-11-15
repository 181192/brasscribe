#!/usr/bin/env python3
"""The release notes Google Play shows for one app's release, from CHANGELOG.md.

    .github/scripts/play-notes.py --app brasscribe|fretscribe --version X.Y.Z --language en-US|no-NO [--changelog FILE]

Prints plain text of at most 500 characters (Play's limit per language): the new features and fixes of that version
that are about the Android app (scope Android, or no scope) and do not name the other app, without links or pull
request numbers. The changelog is written in English, so the no-NO text says so in its first line. Exit 1 when the
version has no section in the changelog.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LIMIT = 500
HEADS = {"en-US": "", "no-NO": "Nytt i denne versjonen (på engelsk):\n"}
NOTHING = {"en-US": "Small improvements and fixes.", "no-NO": "Små forbedringer og rettelser."}
OTHER = {"brasscribe": re.compile(r"\bFretscribe\b"), "fretscribe": re.compile(r"\b(Brasscribe|Play for Android|band)\b", re.I)}
GROUPS = ("New features", "Fixes")


def section(changelog: str, version: str) -> str:
    m = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    if not m:
        raise SystemExit(f"play-notes: no section for {version} in the changelog")
    return m.group(1)


def items(text: str, app: str) -> list[str]:
    out, group = [], ""
    for line in text.splitlines():
        if line.startswith("### "):
            group = line[4:].strip()
            continue
        if group not in GROUPS or not line.startswith("- "):
            continue
        item = line[2:].strip()
        scope = re.match(r"\*\*([^*]+):\*\*\s*", item)
        if scope:
            if scope.group(1) != "Android":
                continue
            item = item[scope.end():]
        item = re.sub(r"\s*\(\[#\d+\]\([^)]*\)\)", "", item)  # ([#123](url))
        item = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", item)  # [text](url) -> text
        item = item.replace("**", "").replace("`", "").strip()
        if item and not OTHER[app].search(item):
            out.append(item)
    return out


def notes(changelog: str, version: str, app: str, language: str) -> str:
    head = HEADS[language]
    found = items(section(changelog, version), app)
    if not found:
        return NOTHING[language]
    text = head
    for item in found:
        line = f"• {item}\n"
        if len(text) + len(line) > LIMIT - 2:
            text += "…\n"
            break
        text += line
    return text.rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--app", required=True, choices=sorted(OTHER))
    p.add_argument("--version", required=True)
    p.add_argument("--language", required=True, choices=sorted(HEADS))
    p.add_argument("--changelog", type=Path, default=Path(__file__).resolve().parents[2] / "CHANGELOG.md")
    a = p.parse_args(argv)
    text = notes(a.changelog.read_text(encoding="utf-8"), a.version, a.app, a.language)
    assert len(text) <= LIMIT, len(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
