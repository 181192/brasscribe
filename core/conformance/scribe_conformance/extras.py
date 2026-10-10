"""Talking score and humanization: Python reference vs Rust on every arranged case.

Both run on the reference's own outputs (brass-band.musicxml, composition.json), so a
difference here is in the talking score or the humanizer, not in the arrangement.

* Talking score (engine/src/brasscribe_engine/talking_score.py): the document JSON and
  the text and HTML exports under several settings.
* Humanization (sounds/humanize.py): every non-drum voice of the Composition as a part,
  on the voice's own ticks and shifted off them, two players, score and performed timing,
  with and without the Composition.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from .canon import json_equal
from .cases import REPO

SETTINGS = [
    ("en", {}),
    ("nb", {"lang": "nb"}),
    ("en-full-concert", {"verbosity": "full", "pitch_mode": "concert", "announce_confident": True}),
    ("nb-brief-helmholtz", {"lang": "nb", "verbosity": "brief", "octave_style": "helmholtz"}),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_TS = _HU = None


def talking():
    global _TS
    if _TS is None:
        _TS = _load("bc_talking_score", REPO / "engine" / "src" / "brasscribe_engine" / "talking_score.py")
    return _TS


def humanizer():
    global _HU
    if _HU is None:
        _HU = _load("bc_humanize", REPO / "sounds" / "humanize.py")
    return _HU


def _cli_settings(s: dict) -> list[str]:
    out = []
    for k, flag in (("lang", "--lang"), ("verbosity", "--verbosity"), ("pitch_mode", "--pitch-mode"),
                    ("octave_style", "--octave-style")):
        if k in s:
            out += [flag, s[k]]
    if s.get("announce_confident"):
        out.append("--announce-confident")
    return out


def talking_rows(binary: Path, src: Path, py: Path, rs: Path) -> list[tuple[str, bool, str]]:
    T = talking()
    xml, comp_p = src / "brass-band.musicxml", src / "composition.json"
    if not xml.exists():
        return []
    comp = json.loads(comp_p.read_text()) if comp_p.exists() else None
    doc = T.build(xml, comp)
    (py / "talking").mkdir(parents=True, exist_ok=True)
    (rs / "talking").mkdir(parents=True, exist_ok=True)
    (py / "talking" / "doc.json").write_text(json.dumps(doc, indent=1))
    rows = []
    for i, (label, s) in enumerate(SETTINGS):
        st = T.Settings(**s)
        (py / "talking" / f"{label}.txt").write_text(T.to_text(doc, st))
        (py / "talking" / f"{label}.html").write_text(T.to_html(doc, st))
        cmd = [str(binary), "talking-score", "--musicxml", str(xml), *(["--composition", str(comp_p)] if comp else []),
               "--text", str(rs / "talking" / f"{label}.txt"), "--html", str(rs / "talking" / f"{label}.html"),
               *(["--json", str(rs / "talking" / "doc.json")] if i == 0 else []), *_cli_settings(s)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            return [("talking", False, p.stderr[-1500:])]
    names = ["doc.json"] + [f"{label}.{ext}" for label, _ in SETTINGS for ext in ("txt", "html")]
    for n in names:
        a, b = py / "talking" / n, rs / "talking" / n
        if n.endswith(".json"):
            same, ok, det = json_equal(a, b)
            det = det or ("" if ok else "parsed equal, bytes differ")
        else:
            ok = a.read_bytes() == b.read_bytes()
            det = "" if ok else _first_diff(a.read_text(), b.read_text())
        rows.append((f"talking:{n}", ok, det))
    return rows


def _first_diff(a: str, b: str) -> str:
    la, lb = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return f"line {i + 1}: py {x!r} rust {y!r}"
    return f"lengths differ: {len(la)} vs {len(lb)} lines"


def humanize_inputs(comp: dict) -> list[tuple[str, list[dict]]]:
    """(part name, ScoreNotes) per non-drum voice, on its ticks and shifted by a 16th."""
    out = []
    for v in comp.get("voices", []):
        if v.get("layer") == "drums" or v.get("role") == "rhythm" or not v.get("notes"):
            continue
        for label, shift, transpose in (("", 0, 0), (" (octave)", 0, 12), (" (off grid)", 6, 0)):
            notes = [{"tick": n["start"] + shift, "dur_tick": n["dur"], "start_s": (n["start"] + shift) / 48,
                      "end_s": (n["start"] + shift + n["dur"]) / 48, "pitch": n["pitch"] + transpose, "velocity": 80}
                     for n in v["notes"]]
            out.append((v["id"] + label, notes))
    return out


def humanize_rows(binary: Path, src: Path, py: Path, rs: Path) -> list[tuple[str, bool, str]]:
    H = humanizer()
    comp_p = src / "composition.json"
    if not comp_p.exists():
        return []
    comp = json.loads(comp_p.read_text())
    perf = H.Performance.load(comp_p)
    has_beats = len(perf.beat_times) >= 2
    (py / "humanize").mkdir(parents=True, exist_ok=True)
    (rs / "humanize").mkdir(parents=True, exist_ok=True)
    runs = []
    for k, (part, notes) in enumerate(humanize_inputs(comp)):
        nf = py / "humanize" / f"notes-{k}.json"
        nf.write_text(json.dumps(notes))
        for player in (0, 3):
            for timing in (("score", "performed") if has_beats else ("score",)):
                for with_comp in (True, False):
                    if timing == "performed" and not with_comp:
                        continue
                    runs.append((part, nf, notes, player, timing, with_comp))
    ok_all, details, n = True, [], 0
    for i, (part, nf, notes, player, timing, with_comp) in enumerate(runs):
        sn = [H.ScoreNote(**x) for x in notes]
        played, detune, stats = H.humanize(sn, part, player, perf=perf if with_comp else None, timing=timing)
        ref = {"notes": [{"start": x.start, "end": x.end, "pitch": x.pitch, "velocity": x.velocity, "staccato": x.staccato,
                          "from_composition": x.from_composition} for x in played], "detune": detune, "stats": stats}
        a, b = py / "humanize" / f"out-{i}.json", rs / "humanize" / f"out-{i}.json"
        a.write_text(json.dumps(ref))
        cmd = [str(binary), "humanize", "--notes", str(nf), "--part", part, "--player", str(player), "--timing", timing,
               "--out", str(b), *(["--composition", str(comp_p)] if with_comp else [])]
        p = subprocess.run(cmd, capture_output=True, text=True)
        n += 1
        if p.returncode != 0:
            ok_all = False
            details.append(f"{part}/{player}/{timing}: {p.stderr[-300:]}")
            continue
        same, ok, det = json_equal(a, b)
        det = det or ("" if ok else "parsed equal, bytes differ")
        if not ok:
            ok_all = False
            details.append(f"{part}/{player}/{timing}/{'comp' if with_comp else 'jitter'}: {det[:300]}")
    return [(f"humanize:{n} runs", ok_all, "; ".join(details[:5]))] if runs else []
