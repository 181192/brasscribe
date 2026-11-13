#!/usr/bin/env python3
"""The third-party licence texts every app ships, written from one list.

    scripts/licences.py build        write licences/dist/<app>.txt for every app
    scripts/licences.py check        fail when a written file is not what the list gives, or the list
                                     no longer matches what the apps are built from
    scripts/licences.py sync-cargo   read the Rust crates and their licences from cargo into
                                     licences/cargo.json (needs cargo; after a change of core/Cargo.lock)

licences/components.json names every component an app ships: its licence, the copyright lines that
must go with it, and the apps that carry it. licences/texts holds each licence's text once. The apps
bundle their file from licences/dist and show it from About (licences/README.md).

`check` reads the dependency lists the builds use (the Gradle version catalogue, the NuGet package
versions, Studio's package.json, core/Cargo.lock): a dependency that is neither a component here nor
listed as not shipped fails it, so a new library cannot ship without its licence. It needs Python's
standard library only.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "licences"
DIST = HERE / "dist"
RULE = "=" * 40  # a line of its own between parts; the apps draw it as a divider

# Where the builds say what they depend on.
GRADLE_CATALOGUE = ROOT / "apps/android/gradle/libs.versions.toml"
NUGET_VERSIONS = [ROOT / "apps/windows/Directory.Packages.props", ROOT / "apps/bandroom/windows/Directory.Packages.props"]
NPM_PACKAGE = ROOT / "studio/package.json"
CARGO_LOCK = ROOT / "core/Cargo.lock"

# The licence a crate is used under when it offers a choice, and the text that goes with each.
CARGO_TEXTS = {"Apache-2.0": "Apache-2.0", "MIT": "MIT", "MPL-2.0": "MPL-2.0", "Zlib": "Zlib", "Unicode-3.0": "Unicode-3.0"}


def manifest() -> dict:
    m = json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    for c in m["components"]:
        apps: list[str] = []
        for a in c["apps"]:
            apps += m["sets"][a[1:]] if a.startswith("@") else [a]
        unknown = [a for a in apps if a not in m["apps"]]
        if unknown:
            raise SystemExit(f"licences: {c['id']} names apps that are not listed: {', '.join(unknown)}")
        c["apps"] = apps
    return m


def crates() -> dict:
    return json.loads((HERE / "cargo.json").read_text(encoding="utf-8"))["crates"]


def used_under(expression: str) -> list[str]:
    """The licences a crate is used under, from its SPDX expression: every part joined by AND, and of a
    choice (OR, or the old "/") Apache-2.0 when it is offered, else the first that has a text here."""
    out = []
    for part in re.split(r"\s+AND\s+", expression.replace("(", "").replace(")", "")):
        offered = [re.sub(r"\s+WITH\s+.*", "", o).strip() for o in re.split(r"\s+OR\s+|/", part)]
        pick = "Apache-2.0" if "Apache-2.0" in offered else next((o for o in offered if o in CARGO_TEXTS), None)
        if pick is None:
            raise SystemExit(f"licences: no text here for a crate under '{expression}': add it to licences/texts "
                             "and to CARGO_TEXTS in scripts/licences.py")
        out.append(pick)
    return out


MARKER = re.compile(r"(\d+\.|\([a-z0-9]{1,3}\)|[a-z]\)|[*•-])\s")


def reflow(text: str) -> str:
    """A licence text with each paragraph on one line, so that a phone and a wide window both wrap it to their
    own width; upstream texts are wrapped at some 70 characters. Paragraphs stay apart, and inside one a new
    line starts at each list marker. Not a word is changed."""
    out = []
    for paragraph in re.split(r"\n[ \t]*\n", text.strip("\n")):
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        joined: list[str] = []
        for line in lines:
            if joined and not MARKER.match(line):
                joined[-1] += " " + line
            else:
                joined.append(line)
        out.append("\n".join(joined))
    return "\n\n".join(out)


def upstream_files(app: str, m: dict) -> list[tuple[dict, Path]]:
    """The notice files a component's makers publish with it, for the version this app carries: the version
    is read from the build's own pin, so a new version asks for its own file."""
    out = []
    for c in m["components"]:
        for u in c.get("upstream", []):
            if app in u["apps"]:
                pin = re.search(u["version_is"], (ROOT / u["version_in"]).read_text(encoding="utf-8"), re.M)
                if not pin:
                    raise SystemExit(f"licences: {u['version_in']} no longer names the version of {c['id']}")
                out.append((c, HERE / "upstream" / u["file"].format(version=pin.group(1))))
    return out


def render(app: str, m: dict, cargo: dict) -> str:
    parts = [c for c in m["components"] if app in c["apps"]]
    texts: list[str] = []
    out = [f"Third-party licences: {m['apps'][app]}", "",
           "This app is licensed under MIT or Apache-2.0, at your choice. It includes the software, fonts, sounds and "
           "models below, which keep their own licences. Each is named with its licence and the notice that goes with "
           "it; the full text of each licence follows the list, once.",
           "", "Contents", ""]
    out += [f"- {c['name']} ({c['licence']})" for c in parts]
    for c in parts:
        out += ["", RULE, "", c["name"], c["url"], f"Licence: {c['licence']}", ""]
        out += c.get("notice", [])
        if c.get("note"):
            out += ([""] if c.get("notice") else []) + [c["note"]]
        if c.get("cargo"):
            out.append("")
            for name, crate in sorted(cargo.items()):
                under = used_under(crate["licence"])
                texts += [CARGO_TEXTS[u] for u in under if CARGO_TEXTS[u] not in texts]
                shown = crate["licence"] if [crate["licence"]] == under else f"{crate['licence']}; used under {' and '.join(under)}"
                out.append(f"- {name} ({shown})" + "".join(f". {n}" for n in crate.get("notice", [])))
        texts += [t for t in c["texts"] if t not in texts]
    for t in texts:
        out += ["", RULE, "", f"Licence text: {t}", "", reflow((HERE / "texts" / f"{t}.txt").read_text(encoding="utf-8"))]
    for c, path in upstream_files(app, m):
        if not path.exists():
            raise SystemExit(f"licences: {path.relative_to(ROOT)} is missing: the build names a version of {c['name']} whose "
                             f"notices are not here. Save the file its makers publish for that version ({c['url']}) under that name")
        notices = reflow(path.read_text(encoding="utf-8"))
        if RULE in notices.split("\n"):
            raise SystemExit(f"licences: {path.relative_to(ROOT)} has a line that is this file's own rule; give RULE another length")
        out += ["", RULE, "", f"Notices published with {c['name']}", "", notices]
    return "\n".join(line.rstrip() for line in "\n".join(out).split("\n")) + "\n"


def build() -> dict[Path, str]:
    m, cargo = manifest(), crates()
    return {DIST / f"{app}.txt": render(app, m, cargo) for app in m["apps"]}


# ---------------------------------------------------------------- what the builds depend on

# Each gives the names a build depends on, with the file that names them.

def gradle_modules() -> dict[str, str]:
    where = str(GRADLE_CATALOGUE.relative_to(ROOT))
    return {n: where for n in re.findall(r'module\s*=\s*"([^"]+)"', GRADLE_CATALOGUE.read_text(encoding="utf-8"))}


def nuget_packages() -> dict[str, str]:
    found: dict[str, list[str]] = {}
    for f in NUGET_VERSIONS:
        for p in re.findall(r'<PackageVersion\s+Include="([^"]+)"', f.read_text(encoding="utf-8")):
            found.setdefault(p, []).append(str(f.relative_to(ROOT)))
    return {p: " and ".join(files) for p, files in found.items()}


def npm_packages() -> dict[str, str]:
    where = str(NPM_PACKAGE.relative_to(ROOT))
    return {n: where for n in json.loads(NPM_PACKAGE.read_text(encoding="utf-8")).get("dependencies", {})}


def locked_crates() -> list[str]:
    """Every crate in core/Cargo.lock that comes from a registry (the workspace's own have no source)."""
    blocks = CARGO_LOCK.read_text(encoding="utf-8").split("[[package]]")[1:]
    return sorted({re.search(r'name = "([^"]+)"', b).group(1) for b in blocks if "source = " in b})


def uncovered(kind: str, names: dict[str, str], m: dict) -> dict[str, str]:
    patterns = [p for c in m["components"] for p in c.get("covers", {}).get(kind, [])] + m["not_shipped"].get(kind, [])
    return {n: where for n, where in names.items() if not any(fnmatch.fnmatchcase(n, p) for p in patterns)}


def problems() -> list[str]:
    m, cargo = manifest(), crates()
    found = []
    for path, text in build().items():
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            found.append(f"{path.relative_to(ROOT)} is not what licences/components.json gives: run scripts/licences.py build")
    stale = sorted(p.name for p in DIST.glob("*.txt") if p.stem not in m["apps"])
    if stale:
        found.append(f"licences/dist holds files of apps that are not listed: {', '.join(stale)}")
    have = {p.stem for p in (HERE / "texts").glob("*.txt")}
    want = {t for c in m["components"] for t in c["texts"]} | {CARGO_TEXTS[u] for c in cargo.values() for u in used_under(c["licence"])}
    if want - have:
        found.append(f"licences/texts lacks: {', '.join(sorted(want - have))}")
    if have - want:
        found.append(f"licences/texts holds texts nothing uses: {', '.join(sorted(have - want))}")
    for c in m["components"]:
        if not c["apps"]:
            found.append(f"{c['id']} is in no app: remove it")
    used = {path.name for app in m["apps"] for _, path in upstream_files(app, m)}
    unused = sorted(p.name for p in (HERE / "upstream").glob("*") if p.name not in used)
    if unused:
        found.append(f"licences/upstream holds files no app's version asks for: {', '.join(unused)}")
    for kind, names in (("maven", gradle_modules()), ("nuget", nuget_packages()), ("npm", npm_packages())):
        for n, where in sorted(uncovered(kind, names, m).items()):
            found.append(f"{n} ({where}) is not in licences/components.json: add it to the component "
                         f"it belongs to (covers.{kind}) with its licence, or to not_shipped.{kind} when no app ships it")
    locked = set(locked_crates())
    if locked != set(cargo):
        found.append("licences/cargo.json is not the crates of core/Cargo.lock"
                     + (f"; new: {', '.join(sorted(locked - set(cargo)))}" if locked - set(cargo) else "")
                     + (f"; gone: {', '.join(sorted(set(cargo) - locked))}" if set(cargo) - locked else "")
                     + ": run scripts/licences.py sync-cargo, then build")
    return found


# ---------------------------------------------------------------- the crates, from cargo

def sync_cargo() -> None:
    """licences/cargo.json from `cargo metadata`: each registry crate's licence, and the copyright lines of its
    licence files where the licence asks for them to be kept (not Apache-2.0, whose text names no holder)."""
    meta = json.loads(subprocess.run(["cargo", "metadata", "--format-version", "1", "--locked"], cwd=ROOT / "core",
                                     check=True, capture_output=True, text=True).stdout)
    table = {}
    for p in meta["packages"]:
        if p["source"] is None:
            continue
        entry = {"licence": p["license"]}
        if used_under(p["license"]) != ["Apache-2.0"]:
            entry["notice"] = copyright_lines(Path(p["manifest_path"]).parent) or [f"Copyright (c) the {p['name']} contributors"]
        table[p["name"]] = entry
    (HERE / "cargo.json").write_text(json.dumps({"crates": dict(sorted(table.items()))}, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")


def copyright_lines(crate: Path) -> list[str]:
    lines = []
    for f in sorted(crate.iterdir()) if crate.is_dir() else []:
        if not re.match(r"(?i)(licen[sc]e|copying)", f.name) or re.search(r"(?i)apache|unlicense", f.name):
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip(" *#/")
            if re.match(r"(?i)(copyright|\(c\)|©)\s", line) and not re.search(r"(?i)notice|holder|owner", line):
                line = re.sub(r"\s*<[^>]*@[^>]*>", "", line)  # the name is the notice; an address is not kept here
                if line not in lines:
                    lines.append(line)
    return lines


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "sync-cargo":
        sync_cargo()
        return 0
    if command == "build":
        DIST.mkdir(exist_ok=True)
        for path, text in build().items():
            path.write_text(text, encoding="utf-8")
            print(path.relative_to(ROOT))
        return 0
    if command == "check":
        found = problems()
        for p in found:
            print(f"licences: {p}", file=sys.stderr)
        return 1 if found else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
