"""Conformance runner: Python reference vs Rust core on the same inputs.

    uv run python -m brasscribe_conformance.run [--only SUBSTR] [--work DIR] [--skip-python] [--musescore]

For every case the Python reference writes to <work>/<case>/py and the Rust
CLI (`brasscribe-core`) to <work>/<case>/rs; Compositions are compared exactly
(parsed JSON, floats bit-equal; byte identity reported too) and MusicXML is
compared after canonicalisation (see canon.py). The Mikkel case is also
compared against the golden output. With --musescore the Rust MusicXML of
every band case is round-tripped through MuseScore.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from .canon import json_equal, musicxml_equal
from .cases import REPO, Case, all_cases, synth_layers

CORE = REPO / "core"
OUTPUTS = {"layers": ["composition.json", "brass-band.musicxml"], "song": ["composition.json", "brass-band.musicxml"],
           "bench": ["composition.json", "brass-band.musicxml"], "lead": ["lead.musicxml"], "quant": ["quant.json"]}


def rust_bin() -> Path:
    subprocess.run(["cargo", "build", "--release", "-q", "-p", "brasscribe-cli"], cwd=CORE, check=True)
    return CORE / "target" / "release" / "brasscribe-core"


def rust_cmd(binary: Path, case: Case, out: Path) -> list[str]:
    a = case.args
    b = str(binary)
    if case.kind == "layers":
        return [b, "arrange-layers", "--layers", str(a["layers"]), "--beats", str(a["beats"]), "--out", str(out),
                "--title", a["title"], *(["--solo-contour", str(a["contour"])] if "contour" in a else [])]
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


def compare(ref_dir: Path, rs_dir: Path, names: list[str]) -> list[tuple[str, bool, str]]:
    rows = []
    for name in names:
        a, b = ref_dir / name, rs_dir / name
        if not a.exists() or not b.exists():
            rows.append((name, False, f"missing: ref={a.exists()} rs={b.exists()}"))
        elif name.endswith(".json"):
            same, byte_same, detail = json_equal(a, b)
            rows.append((name, same, detail or ("" if byte_same else "(parsed equal, bytes differ)")))
        else:
            same, detail = musicxml_equal(a, b)
            rows.append((name, same, detail))
    return rows


def musescore_roundtrip(xml: Path) -> bool:
    out = xml.with_name(xml.stem + ".mscore.musicxml")
    out.unlink(missing_ok=True)
    # MuseScore 4.7 aborts on shutdown after writing: trust the file, not the exit code.
    subprocess.run(["mscore", "-o", str(out), str(xml)], capture_output=True, timeout=600)
    return out.exists() and out.stat().st_size > 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=REPO / "data" / "runs" / "core-conformance")
    ap.add_argument("--only")
    ap.add_argument("--skip-python", action="store_true", help="reuse existing reference outputs")
    ap.add_argument("--skip-rust", action="store_true")
    ap.add_argument("--musescore", action="store_true")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    cases = all_cases(args.work, args.only)
    binary = None if args.skip_rust else rust_bin()
    results = []
    for case in cases:
        d = args.work / case.id
        py, rs = d / "py", d / "rs"
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
        rows = compare(py, rs, OUTPUTS[case.kind]) if p.returncode == 0 else [("rust", False, p.stderr[-2000:])]
        ok = all(r[1] for r in rows)
        entry = {"case": case.id, "ok": ok, "py_s": round(t_py, 2), "rs_s": round(t_rs, 3),
                 "checks": [{"file": n, "ok": s, "detail": det} for n, s, det in rows]}
        if case.golden is not None and p.returncode == 0:
            # Informational: the golden set is re-saved deliberately, so it may lag the reference.
            entry["golden"] = {n: compare(case.golden, rs, [n])[0][1] for n in OUTPUTS[case.kind]}
        if args.musescore and ok and case.kind in ("layers", "song", "bench"):
            entry["musescore"] = musescore_roundtrip(rs / "brass-band.musicxml")
        results.append(entry)
        mark = "OK  " if ok else "DIFF"
        print(f"{mark} {case.id:70s} py {t_py:6.2f}s rs {t_rs:6.3f}s" + (
            f" mscore={'ok' if entry.get('musescore') else 'FAIL'}" if "musescore" in entry else "") + (
            f" golden={entry['golden']}" if "golden" in entry else ""), flush=True)
        for n, s, det in rows:
            if not s:
                print(f"     {n}: {det[:1500]}")
    if results:
        files = [c for r in results for c in r["checks"]]
        n_ok = sum(r["ok"] for r in results)
        print(f"\ncases identical: {n_ok}/{len(results)}; files identical: {sum(c['ok'] for c in files)}/{len(files)}")
        if args.report:
            args.report.write_text(json.dumps(results, indent=1))
        sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
