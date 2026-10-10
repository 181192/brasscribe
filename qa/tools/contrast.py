# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""WCAG contrast and colour-vision-deficiency check for the design tokens.

Reads docs/accessibility/design-tokens.json and prints a markdown report:
  - WCAG 2.x contrast ratio for every listed pair in every theme, against its minimum
  - CIEDE2000 colour difference for the "distinguish" pairs under normal vision and
    simulated protanopia, deuteranopia, tritanopia (Machado et al. 2009, severity 1.0)
    and achromatopsia (luminance only)

Exit code 1 if any contrast pair is below its minimum (use in CI). Colour differences
below DE_MIN are reported as "weak"; they do not fail the run because uncertainty is
also encoded by notehead shape (WCAG 1.4.1).

    uv run qa/tools/contrast.py > qa/reports/contrast-tokens.md

With --tokens it reads a W3C Design Tokens (DTCG) file instead: colour roles under
color.<mode>.<role>.$value.hex, and the modes, pairs and distinguish lists under the product's
own $extensions entry (e.g. "no.brasscribe"; whichever single entry has modes and contrast):

    uv run qa/tools/contrast.py --tokens design/tokens/tokens.json > qa/reports/contrast-design-tokens.md

With --brands it checks every brand of design/tokens/brands.json in every one of its modes, and that each
brand's committed report is the one its tokens give (--brands --write rewrites the reports):

    uv run qa/tools/contrast.py --brands
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS = ROOT / "docs" / "accessibility" / "design-tokens.json"
BRANDS = ROOT / "design" / "tokens" / "brands.json"
DE_MIN = 20.0  # heuristic: CIEDE2000 below this reads as "similar" at notehead size

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}


def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_srgb(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminance(rgb: tuple[float, float, float]) -> float:
    # WCAG 2.x uses the 0.03928 threshold; the difference from 0.04045 is negligible at 8 bit.
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(hex_rgb(a)), luminance(hex_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def simulate(rgb: tuple[float, float, float], kind: str) -> tuple[float, float, float]:
    lin = [to_linear(c) for c in rgb]
    if kind == "achroma":
        y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        return (to_srgb(y),) * 3  # type: ignore[return-value]
    m = MACHADO[kind]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return tuple(to_srgb(c) for c in out)  # type: ignore[return-value]


def lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (to_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(l1: tuple, l2: tuple) -> float:
    L1, a1, b1 = l1
    L2, a2, b2 = l2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cm = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cm ** 7 / (cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dL = L2 - L1
    dC = c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    dH = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    Lm = (L1 + L2) / 2
    cmp_ = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hm = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hm = (h1p + h2p + 360) / 2
    else:
        hm = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    dtheta = 30 * math.exp(-(((hm - 275) / 25) ** 2))
    rc = 2 * math.sqrt(cmp_ ** 7 / (cmp_ ** 7 + 25 ** 7))
    sl = 1 + (0.015 * (Lm - 50) ** 2) / math.sqrt(20 + (Lm - 50) ** 2)
    sc = 1 + 0.045 * cmp_
    sh = 1 + 0.015 * cmp_ * t
    rt = -math.sin(math.radians(2 * dtheta)) * rc
    return math.sqrt((dL / sl) ** 2 + (dC / sc) ** 2 + (dH / sh) ** 2 + rt * (dC / sc) * (dH / sh))


def delta_e(a: str, b: str, kind: str | None) -> float:
    ra, rb = hex_rgb(a), hex_rgb(b)
    if kind:
        ra, rb = simulate(ra, kind), simulate(rb, kind)
    return ciede2000(lab(ra), lab(rb))


def token_extension(raw: dict) -> dict:
    """The product's extension block: the one entry under $extensions that lists modes and contrast pairs."""
    extensions = raw.get("$extensions")
    extensions = extensions if isinstance(extensions, dict) else {}
    found = [v for v in extensions.values() if isinstance(v, dict) and "modes" in v and "contrast" in v]
    if len(found) != 1:
        raise SystemExit(f"expected one $extensions entry with modes and contrast, found {len(found)}")
    return found[0]


def load_dtcg(path: Path) -> dict:
    """Flatten a DTCG token file into the {themes, pairs, distinguish, legacy} shape used below."""
    raw = json.loads(path.read_text())
    ext = token_extension(raw)
    themes = {}
    for mode in ext["modes"]:
        themes[mode] = {role: tok["$value"]["hex"] for role, tok in raw["color"][mode].items()
                        if isinstance(tok, dict) and tok.get("$type") == "color"}
    return {"themes": themes, "pairs": ext["contrast"]["pairs"],
            "distinguish": ext["contrast"]["distinguish"],
            "legacy": ext.get("a11yCompat", {}).get("legacy", {})}


def brands() -> list[dict]:
    """Every brand of the design system: name, token file and contrast report, from the repository root."""
    return json.loads(BRANDS.read_text())["brands"]


def check_brands(write: bool = False) -> int:
    """Every brand, every mode: no pair below its minimum, and the committed report is the current one."""
    bad = 0
    for brand in brands():
        data = load_dtcg(ROOT / brand["tokens"])
        text, failures = report(data, f"uv run qa/tools/contrast.py --tokens {brand['tokens']}", brand["tokens"])
        path = ROOT / brand["contrast-report"]
        if write:
            path.write_text(text + "\n")
        stale = not path.exists() or path.read_text() != text + "\n"
        print(f"{brand['name']}: {len(data['themes'])} modes, {failures} contrast failures"
              + (f"; {brand['contrast-report']} is out of date (run with --brands --write)" if stale else ""))
        bad += failures + stale
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--brands"]:
        return check_brands(write=argv[1:] == ["--write"])
    if argv[:1] == ["--tokens"] and len(argv) == 2:
        src = Path(argv[1])
        data = load_dtcg(src if src.is_absolute() or src.exists() else ROOT / src)
        cmd, label = f"uv run qa/tools/contrast.py --tokens {argv[1]}", argv[1]
    else:
        data = json.loads(TOKENS.read_text())
        cmd, label = "uv run qa/tools/contrast.py", "docs/accessibility/design-tokens.json"
    text, failures = report(data, cmd, label)
    print(text)
    return 1 if failures else 0


def report(data: dict, cmd: str, label: str) -> tuple[str, int]:
    """The markdown report of a palette and the number of contrast pairs below their minimum."""
    failures = 0
    out = ["# Contrast and colour-vision report", "",
           f"Generated by `{cmd}` from `{label}`. "
           "Do not edit by hand.", ""]
    for theme, tok in data["themes"].items():
        out += [f"## {theme}", "", "| foreground | background | ratio | min | SC | result |", "|---|---|---|---|---|---|"]
        for fg, bg, minimum, sc in data["pairs"]:
            r = contrast(tok[fg], tok[bg])
            ok = r + 1e-9 >= minimum
            failures += 0 if ok else 1
            out.append(f"| {fg} `{tok[fg]}` | {bg} `{tok[bg]}` | {r:.2f}:1 | {minimum}:1 | {sc} | {'pass' if ok else '**FAIL**'} |")
        out += ["", f"CIEDE2000 difference (weak below {DE_MIN:.0f}; shape encoding is required regardless):", "",
                "| pair | normal | protan | deutan | tritan | achroma |", "|---|---|---|---|---|---|"]
        for a, b in data["distinguish"]:
            cells = []
            for kind in (None, "protan", "deutan", "tritan", "achroma"):
                d = delta_e(tok[a], tok[b], kind)
                cells.append(f"{d:.1f}" + ("" if d >= DE_MIN else " weak"))
            out.append(f"| {a} / {b} | " + " | ".join(cells) + " |")
        out.append("")
    legacy = data.get("legacy", {}).get("light", {})
    if legacy:
        light = data["themes"]["light"]
        out += ["## Current engine output (reference)", "", "| colour | vs bg | vs ink (normal / protan / deutan / tritan / achroma) |", "|---|---|---|"]
        for name, hexv in legacy.items():
            des = " / ".join(f"{delta_e(hexv, light['ink'], k):.1f}" for k in (None, "protan", "deutan", "tritan", "achroma"))
            out.append(f"| {name} `{hexv}` | {contrast(hexv, light['bg']):.2f}:1 | {des} |")
        out.append("")
    out.append(f"Contrast failures: {failures}")
    return "\n".join(out), failures


if __name__ == "__main__":
    sys.exit(main())
