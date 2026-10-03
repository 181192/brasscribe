#!/usr/bin/env python3
"""What changed in the screen catalogues' screenshots: a page and a list (apps/android/scripts/screenshots.sh compare).

    screenshot_report.py <before dir> <roborazzi results dir> <report dir>

Reads Roborazzi's results-summary.json of each app, writes <report dir>/index.html and summary.md with
the images of every screen that changed, appeared or went away, and exits 1 when there is any.
"""
import html
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    before, results, report = (Path(a) for a in sys.argv[1:4])
    images = report / "images"
    images.mkdir(parents=True, exist_ok=True)
    had = {p.relative_to(before).as_posix() for p in before.rglob("*.png")
           if not p.stem.endswith(("_compare", "_actual"))}
    seen, changed, added = set(), [], []
    for summary in sorted(results.glob("*/results-summary.json")):
        for r in json.loads(summary.read_text())["results"]:
            golden = Path(r["golden_file_path"])
            name = golden.as_posix().split("/outputs/roborazzi/", 1)[-1]
            seen.add(name)
            if r["type"] == "changed":
                shown = images / name.replace("/", "--").replace(".png", "-compare.png")
                shutil.copy(r["compare_file_path"], shown)
                changed.append((name, shown.name, r.get("diff_percentage")))
            elif r["type"] == "added" and had:
                shown = images / name.replace("/", "--")
                shutil.copy(r.get("actual_file_path") or golden, shown)
                added.append((name, shown.name))
    gone = sorted(had - seen) if seen else []

    lines = [f"Screenshots: {len(seen)} screens, {len(changed)} changed, {len(added)} new, {len(gone)} gone."]
    if not had:
        lines.append("The commit compared with has no screen catalogue: there was nothing to compare with.")
    lines += [f"- changed: `{n}` ({p * 100:.2f} % of its pixels)" if p is not None else f"- changed: `{n}`" for n, _, p in changed]
    lines += [f"- new: `{n}`" for n, _ in added] + [f"- gone: `{n}`" for n in gone]
    (report / "summary.md").write_text("\n".join(lines) + "\n")

    def block(title: str, rows: str) -> str:
        return f"<h2>{html.escape(title)}</h2>{rows}" if rows else ""

    page = ["<!doctype html><meta charset=utf-8><title>Screenshots</title>",
            "<style>body{font:16px system-ui;margin:16px}img{max-width:100%;border:1px solid #ccc}</style>",
            f"<h1>Screenshots</h1><p>{html.escape(lines[0])}</p>",
            "<p>Each changed screen: before, the difference, after.</p>",
            block("Changed", "".join(f"<h3>{html.escape(n)}</h3><img src='images/{html.escape(f)}'>" for n, f, _ in changed)),
            block("New", "".join(f"<h3>{html.escape(n)}</h3><img src='images/{html.escape(f)}'>" for n, f in added)),
            block("Gone", "".join(f"<p>{html.escape(n)}</p>" for n in gone))]
    (report / "index.html").write_text("\n".join(page))
    print("\n".join(lines))
    return 1 if (changed or added or gone) else 0


if __name__ == "__main__":
    sys.exit(main())
