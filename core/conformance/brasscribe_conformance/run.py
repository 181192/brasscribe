"""Conformance runner: Python reference vs Rust core on the same inputs.

    uv run python -m brasscribe_conformance.run [--only SUBSTR] [--work DIR] [--skip-python] [--musescore]

For every case the Python reference writes to <work>/<case>/py and the Rust
CLI (`brasscribe-core`) to <work>/<case>/rust. Every file the reference wrote
is compared: JSON exactly (parsed, floats bit-equal; byte identity reported
too), MusicXML after canonicalisation (see canon.py), including the split
parts. The Mikkel case is also compared file by file against the golden
output in data/golden/mikkel-arranged-band. With --musescore every Rust score
and lead sheet is round-tripped through MuseScore in one batched launch.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

from . import extras
from .canon import json_equal, musicxml_equal
from .cases import REPO, Case, all_cases, synth_layers

CORE = REPO / "core"
OUTPUTS = {"layers": ["composition.json", "brass-band.musicxml"], "song": ["composition.json", "brass-band.musicxml"],
           "bench": ["composition.json", "brass-band.musicxml"], "lead": ["lead.musicxml"], "quant": ["quant.json"]}
IGNORED = {".pdf", ".mp3", ".mid", ".wav", ".brf"}


def rust_bin() -> Path:
    subprocess.run(["cargo", "build", "--release", "-q", "-p", "brasscribe-cli"], cwd=CORE, check=True)
    return CORE / "target" / "release" / "brasscribe-core"


def rust_cmd(binary: Path, case: Case, out: Path) -> list[str]:
    a = case.args
    b = str(binary)
    if case.kind == "layers":
        return [b, "arrange-layers", "--layers", str(a["layers"]), "--beats", str(a["beats"]), "--out", str(out),
                "--title", a["title"], *(["--solo-contour", str(a["contour"])] if "contour" in a else []),
                *a.get("options", [])]
    if case.kind == "song":
        return [b, "arrange-song", "--beats", str(a["beats"]), "--melody", str(a["melody"]), "--melody-support",
                str(a["support"]), "--bass", str(a["bass"]), "--harmony", *map(str, a["harmony"]), "--out", str(out),
                "--title", a["title"]]
    if case.kind == "lead":
        return [b, "lead-sheet", "--beats", str(a["beats"]), "--melody", str(a["melody"]), "--melody-support",
                str(a["support"]), "--bass", str(a["bass"]), "--out", str(out / "lead.musicxml"), "--title", a["title"]]
    if case.kind == "bench":
        return [b, "arrange-reference", "--reference", str(a["reference"]), "--out", str(out), "--title", a["title"]]
    if case.kind == "quant":
        return [b, "quantize", "--reference", str(a["reference"]), "--beats", str(a["beats"]), "--out", str(out / "quant.json")]
    raise ValueError(case.kind)


def outputs_of(ref_dir: Path, kind: str) -> list[str]:
    """Every symbolic file the reference wrote (relative paths), scores and parts included."""
    names = set(OUTPUTS[kind])
    if ref_dir.exists():
        for p in ref_dir.rglob("*"):
            rel = p.relative_to(ref_dir)
            if rel.parts[0] in ("talking", "humanize"):  # compared by extras
                continue
            if p.is_file() and p.suffix not in IGNORED and ".mscore." not in p.name:
                names.add(str(p.relative_to(ref_dir)))
    return sorted(names)


def from_composition(binary: Path, py: Path, rs: Path) -> list[tuple[str, bool, str]]:
    """The app path: the reference's composition.json read back by Rust, re-serialised
    (must give the same bytes) and arranged to MusicXML (must match the reference score)."""
    rows = []
    comp = py / "composition.json"
    p = subprocess.run([str(binary), "normalize", "--composition", str(comp), "--out", str(rs / "normalized.json")],
                       capture_output=True, text=True)
    same = p.returncode == 0 and (rs / "normalized.json").read_bytes() == comp.read_bytes()
    rows.append(("composition.json (read back)", same, "" if same else p.stderr[-500:] or "bytes differ"))
    p = subprocess.run([str(binary), "musicxml", "--composition", str(comp), "--out", str(rs / "from-composition.musicxml")],
                       capture_output=True, text=True)
    if p.returncode != 0:
        rows.append(("brass-band.musicxml (from composition)", False, p.stderr[-500:]))
    else:
        same, detail = musicxml_equal(py / "brass-band.musicxml", rs / "from-composition.musicxml")
        rows.append(("brass-band.musicxml (from composition)", same, detail))
    return rows


def compare(ref_dir: Path, rs_dir: Path, names: list[str]) -> list[tuple[str, bool, str]]:
    rows = []
    for name in names:
        a, b = ref_dir / name, rs_dir / name
        if not a.exists() or not b.exists():
            rows.append((name, False, f"missing: ref={a.exists()} rs={b.exists()}"))
        elif name.endswith(".json"):
            same, byte_same, detail = json_equal(a, b)
            rows.append((name, same, detail or ("" if byte_same else "(parsed equal, bytes differ)")))
        elif name.endswith((".txt", ".html")):
            same = a.read_bytes() == b.read_bytes()
            rows.append((name, same, "" if same else "text differs"))
        else:
            same, detail = musicxml_equal(a, b)
            rows.append((name, same, detail))
    return rows


def musescore_batch(items: list[tuple[str, Path, Path | None]]) -> dict[str, dict]:
    """Round-trip (case id, musicxml, composition or None) through MuseScore in ONE launch, then
    compare each band score's sounding pitches with the reference arrangement of its composition."""
    sys.path.insert(0, str(REPO / "eval"))
    from brasscribe_eval import musescore_roundtrip as mr  # noqa: PLC0415
    from brasscribe_music import musescore  # noqa: PLC0415

    jobs = []
    for _, xml, _ in items:
        out = xml.with_name(xml.stem + ".mscore.musicxml")
        out.unlink(missing_ok=True)
        jobs.append((xml, out))
    musescore.convert_many(jobs)  # one launch; success is judged by the output files
    # The check below must not launch MuseScore again: the re-exports exist already.
    mr.musescore.convert = lambda src, out, **kw: Path(out).exists()
    res = {}
    for (cid, xml, comp), (_, out) in zip(items, jobs):
        written = out.exists() and out.stat().st_size > 0
        match = written
        if written and comp is not None:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    match = bool(mr.check(xml, comp))
            except SystemExit:
                match = False
        res[cid] = {"written": written, "pitches_match": match}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=REPO / "data" / "runs" / "core-conformance")
    ap.add_argument("--only")
    ap.add_argument("--skip-python", action="store_true", help="reuse existing reference outputs")
    ap.add_argument("--skip-rust", action="store_true")
    ap.add_argument("--musescore", action="store_true")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--no-extras", action="store_true", help="skip the talking-score and humanize checks")
    args = ap.parse_args()
    cases = all_cases(args.work, args.only)
    binary = None if args.skip_rust else rust_bin()
    results = []
    ms_items: list[tuple[str, Path, Path | None]] = []
    for case in cases:
        d = args.work / case.id
        py, rs = d / "py", d / "rust"
        if case.kind == "layers" and "song" in case.args:
            synth_layers(case.args["song"], case.args["layers"])
        t0 = time.time()
        if not args.skip_python or not all((py / n).exists() for n in OUTPUTS[case.kind]):
            from . import reference
            reference.run(case, py)
        t_py = time.time() - t0
        if binary is None:
            continue
        rs.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        p = subprocess.run(rust_cmd(binary, case, rs), capture_output=True, text=True)
        t_rs = time.time() - t0
        names = outputs_of(py, case.kind)
        rows = compare(py, rs, names) if p.returncode == 0 else [("rust", False, p.stderr[-2000:])]
        if case.kind in ("layers", "song", "bench") and p.returncode == 0:
            rows += from_composition(binary, py, rs)
            if not args.no_extras:
                rows += extras.talking_rows(binary, py, py, rs) + extras.humanize_rows(binary, py, py, rs)
        if case.golden is not None and p.returncode == 0:
            # The engine's accessible exports: the talking score is ported (written here from the Rust score),
            # braille (music21's translator) is not.
            subprocess.run([str(binary), "talking-score", "--musicxml", str(rs / "brass-band.musicxml"), "--composition",
                            str(rs / "composition.json"), "--json-utf8", str(rs / "talking-score.json"),
                            "--html", str(rs / "talking-score.html"), "--text", str(rs / "talking-score.txt")], check=True)
            gold = [n for n in outputs_of(case.golden, case.kind) if (case.golden / n).exists() and not n.endswith(".brf")]
            rows += [(f"golden:{n}", s, det) for n, s, det in compare(case.golden, rs, gold)]
        ok = all(r[1] for r in rows)
        entry = {"case": case.id, "ok": ok, "py_s": round(t_py, 2), "rs_s": round(t_rs, 3),
                 "checks": [{"file": n, "ok": s, "detail": det} for n, s, det in rows],
                 "paths": {"py": str(py.relative_to(args.work)), "rust": str(rs.relative_to(args.work))}}
        if args.musescore and p.returncode == 0 and case.kind in ("layers", "song", "bench"):
            ms_items.append((case.id, rs / "brass-band.musicxml", rs / "composition.json"))
        elif args.musescore and p.returncode == 0 and case.kind == "lead":
            ms_items.append((case.id, rs / "lead.musicxml", None))
        results.append(entry)
        mark = "OK  " if ok else "DIFF"
        print(f"{mark} {case.id:70s} py {t_py:6.2f}s rs {t_rs:6.3f}s files {sum(r[1] for r in rows)}/{len(rows)}", flush=True)
        for n, s, det in rows:
            if not s:
                print(f"     {n}: {det[:1500]}")
    if ms_items:
        ms = musescore_batch(ms_items)
        for r in results:
            if r["case"] in ms:
                r["musescore"] = ms[r["case"]]
                if not (ms[r["case"]]["written"] and ms[r["case"]]["pitches_match"]):
                    print(f"MSCORE {r['case']}: {ms[r['case']]}")
    if results:
        files = [c for r in results for c in r["checks"]]
        n_ok = sum(r["ok"] for r in results)
        print(f"\ncases identical: {n_ok}/{len(results)}; files identical: {sum(c['ok'] for c in files)}/{len(files)}")
        gold = [c for r in results for c in r["checks"] if c["file"].startswith("golden:")]
        if gold:
            print(f"golden files identical: {sum(c['ok'] for c in gold)}/{len(gold)}")
        if ms_items:
            ms = [r["musescore"] for r in results if "musescore" in r]
            print(f"musescore round trip: file written {sum(m['written'] for m in ms)}/{len(ms)}, "
                  f"sounding pitches match {sum(m['pitches_match'] for m in ms)}/{len(ms)}")
        report = write_report(args.work, results)
        if args.report:
            args.report.write_text(json.dumps(results, indent=1))
        print(f"report: {report}")
        sys.exit(0 if n_ok == len(results) else 1)


def write_report(work: Path, results: list[dict]) -> Path:
    """Summary for Studio: <work>/report.json, one row per (set, item, stage)."""
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    version = subprocess.run([str(CORE / "target" / "release" / "brasscribe-core"), "version"], capture_output=True,
                             text=True).stdout.strip()
    rows = []
    for r in results:
        parts = r["case"].split("/")
        s, item, stage = (parts[0], parts[0], parts[1]) if len(parts) == 2 else (parts[0], parts[1], parts[2])
        failed = [c for c in r["checks"] if not c["ok"]]
        missing = any(c["detail"].startswith("missing") for c in failed)
        row = {"set": s, "item": item, "stage": stage, "status": "pass" if r["ok"] else ("missing" if missing else "fail"),
               "diffs": len(failed), "files": len(r["checks"]), "py": r["paths"]["py"], "rust": r["paths"]["rust"]}
        if failed:
            row["detail"] = "; ".join(f"{c['file']}: {c['detail'][:300]}" for c in failed)
        if "musescore" in r:
            row["musescore"] = r["musescore"]
        gold = [c for c in r["checks"] if c["file"].startswith("golden:")]
        if gold:
            row["golden"] = {c["file"][7:]: c["ok"] for c in gold}
        rows.append(row)
    out = work / "report.json"
    out.write_text(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git_sha": sha, "core_version": version,
                               "sets": rows}, indent=1))
    return out


if __name__ == "__main__":
    main()
