"""Print a markdown summary table from convert/reports/*.json (plain Python, no dependencies).

  python3 convert/summarize.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parent / "reports"


def _f1(entry: dict) -> tuple[float, str]:
    if "note_f1" in entry:
        return entry["note_f1"]["f1"], f"{entry['note_f1']['f1']:.4f} (min clip {entry['note_f1'].get('min_f1', 1):.3f})"
    if "beat_f1" in entry:
        b, d = entry["beat_f1"]["f1"], entry["downbeat_f1"]["f1"]
        return min(b, d), f"beat {b:.4f} / downbeat {d:.4f}"
    s, p = entry["swift_f0_note_f1"]["f1"], entry["basic_pitch_note_f1"]["f1"]
    return min(s, p), f"SwiftF0 {s:.4f} / BP {p:.4f}; SDR min {entry['sdr_db_min']:.1f} dB"


def _size(report: dict, backend: str) -> str:
    arts = report.get("artifacts", {})
    for name, meta in arts.items():
        stem = name.split("/")[-1]
        tokens = [t for t in backend.replace("onnx1500", "1500").split("-") if t not in ("ort", "cpu", "coreml", "ALL",
                  "CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "onnx", "upstream")]
        kind = ".mlpackage" if backend.startswith("coreml") else ".onnx"
        if stem.endswith(kind) and all(t in stem for t in tokens):
            return f"{meta['size_bytes'] / 2**20:.1f} MB"
    return ""


def main() -> None:
    print("| model | backend | size | parity vs reference | latency (s) | peak RSS (MB) | pass |")
    print("|---|---|---|---|---|---|---|")
    for path in sorted(REPORTS.glob("*.json")):
        r = json.loads(path.read_text())
        for backend, entry in r["parity"].items():
            _, text = _f1(entry)
            bench = r.get("benchmarks", {}).get(backend, {})
            lat = f"{bench['median_s']:.3f} / {bench['audio_s']:.0f} s audio" if "median_s" in bench else ""
            mem = f"{bench['peak_rss_mb']:.0f}" if "peak_rss_mb" in bench else ""
            ok = "pass" if r["pass"].get(backend) else "FAIL"
            print(f"| {r['model']} | {backend} | {_size(r, backend.split('/')[-1])} | {text} | {lat} | {mem} | {ok} |")
        for backend, why in r.get("blocked", {}).items():
            print(f"| {r['model']} | {backend} | | blocked: {why} | | | FAIL |")


if __name__ == "__main__":
    main()
