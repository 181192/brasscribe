# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate platform code from a brand's design tokens.

    uv run design/tokens/build.py                    # write every brand's outputs
    uv run design/tokens/build.py --check            # exit 1 if any output is missing or out of date (CI)
    uv run design/tokens/build.py --brand fretscribe # one brand, by its name in brands.json

The brands are listed in design/tokens/brands.json: a token file and the folder its outputs go to. A token
file that is not listed (a test, a trial) is built with --tokens FILE --out DIR.

    --brand NAME    one brand of brands.json
    --tokens FILE   a token file that is not in brands.json; needs --out
    --out DIR       where its outputs go. Files in DIR's generated folders that this run does not write are
                    deleted, so a brand never shares another's folder.
    --only PLATFORM write that platform only (apple, android, windows, web); the icon map and the
                    accessibility palette are left alone

Names. Every brand gets the same neutral names (Scribe*, --scribe-*; design/tokens/neutral.json lists the
roles), so shared code compiles against any brand, and its own names for everything (its product name and
its prefix: Brasscribe*, Bc*, --bc-*), where its own roles live. design/tokens/README.md has the rule and
the map. The Android theme is the exception until the Android apps use the neutral names: every brand's is
written under Brasscribe's names, through the map in $extensions.<brand>.android (see android_source).

Inputs:  the brand's tokens.json (DTCG), design/tokens/neutral.json, design/tokens/icons.json,
         design/brand/icons/**, and the fonts the token file names
Outputs, for Brasscribe (another brand's have its own name and prefix, in its own folder):
         design/dist/apple/      BrasscribeDesign.xcassets, BrasscribeDesign.swift, Fonts/
         design/dist/android/    kotlin/no/brasscribe/design/*.kt, res/drawable/ic_bc_*.xml, res/font/
         design/dist/windows/    BrasscribeTheme.xaml, BrasscribePinkTheme.xaml, Assets/Fonts/
         design/dist/web/        brasscribe.css, fonts.css, studio-compat.css, icons/*.svg, fonts/
         design/dist/icon-map.md
         docs/accessibility/design-tokens.json (the accessibility palette, kept in its existing shape)

Every output is a pure function of the inputs: no timestamps, sorted where order is free.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BRAND = ROOT / "design" / "brand"
DEFAULT_TOKENS = HERE / "tokens.json"
DEFAULT_DIST = ROOT / "design" / "dist"
# The default tokens name the roles and groups of the generated Android API, whichever product is built.
API = json.loads(DEFAULT_TOKENS.read_text())
# The roles every brand has, under the names shared code uses.
NEUTRAL = json.loads((HERE / "neutral.json").read_text())
# Every brand: its token file and the folder its outputs go to.
BRANDS = json.loads((HERE / "brands.json").read_text())["brands"]
NEUTRAL_PREFIX = "scribe"  # --scribe-text, ScribeTextBrush, ScribeTheme: no brand may take it


def check_brands(brands: list[dict]) -> None:
    """brands.json is well formed: every brand has a name, a token file and a folder, each its own."""
    for i, brand in enumerate(brands):
        for key in ("name", "tokens", "out"):
            if not isinstance(brand.get(key), str) or not brand[key]:
                raise SystemExit(f"design/tokens/brands.json: brand {brand.get('name') or i + 1} has no '{key}'")
    for key, what in (("name", "name"), ("tokens", "token file"), ("out", "output folder")):
        seen: dict[str, str] = {}
        for brand in brands:
            value = brand[key].lower() if key == "name" else (ROOT / brand[key]).resolve().as_posix()
            if value in seen:
                raise SystemExit(f"design/tokens/brands.json: {seen[value]} and {brand['name']} have the same {what} ({brand[key]})")
            seen[value] = brand["name"]


check_brands(BRANDS)
ICONS = json.loads((HERE / "icons.json").read_text())["actions"]
PLATFORMS = ("apple", "android", "windows", "web")


def rel(path: Path) -> str:
    """A path as the docs and headers name it: from the repository root when it is inside it."""
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def product_extension(tokens: dict) -> tuple[str, dict]:
    """The product's block under $extensions: the one entry that lists modes and contrast pairs."""
    found = [(k, v) for k, v in tokens.get("$extensions", {}).items() if isinstance(v, dict) and "modes" in v and "contrast" in v]
    if len(found) != 1:
        raise SystemExit(f"expected one $extensions entry with modes and contrast, found {len(found)}")
    return found[0]


def brand_of(tokens: Path) -> dict | None:
    """The entry of brands.json a token file belongs to."""
    return next((b for b in BRANDS if (ROOT / b["tokens"]).resolve() == tokens.resolve()), None)


def configure(tokens: Path = DEFAULT_TOKENS, out: Path = DEFAULT_DIST, only: str | None = None) -> None:
    """Choose the token file, the output folder and the platform; the defaults are Brasscribe's."""
    global TOKENS_FILE, TOKENS, EXT, MODES, DIST, HEADER, ONLY, ANDROID, PRODUCT, CSS, KEY, PINK
    TOKENS_FILE, DIST = tokens.resolve(), out.resolve()
    TOKENS = json.loads(TOKENS_FILE.read_text())
    namespace, EXT = product_extension(TOKENS)
    MODES = EXT["modes"]
    ANDROID = EXT.get("android", {})
    PRODUCT = namespace.rsplit(".", 1)[-1].capitalize()
    # The brand's short prefix: --bc-text in CSS, BcTextBrush in XAML.
    CSS = EXT.get("prefix", PRODUCT.lower())
    KEY = CSS.capitalize()
    PINK = "pink" in MODES and "pink-dark" in MODES
    ONLY = only
    HEADER = f"Generated by design/tokens/build.py from {rel(TOKENS_FILE)}. Do not edit."
    for brand in BRANDS:
        if DIST == (ROOT / brand["out"]).resolve() and TOKENS_FILE != (ROOT / brand["tokens"]).resolve():
            raise SystemExit(f"{brand['out']} is the output folder of {brand['name']} (design/tokens/brands.json): "
                             f"give {rel(TOKENS_FILE)} its own --out")
    check_tokens()


def fail(message: str):
    raise SystemExit(f"{rel(TOKENS_FILE)}: {message}")


def check_tokens() -> None:
    """The token file has what the generator reads, so a brand that lacks something is told what, in words."""
    if not re.fullmatch(r"[a-z][a-z0-9]*", CSS):
        fail(f"the prefix '{CSS}' must be lower-case letters and digits, starting with a letter")
    if NEUTRAL_PREFIX in (CSS, PRODUCT.lower()):
        fail(f"'{NEUTRAL_PREFIX}' is the prefix of the neutral names; a brand needs its own")
    for brand in BRANDS:  # no two brands with one prefix: their variables and keys would be the same
        other = (ROOT / brand["tokens"]).resolve()
        if other != TOKENS_FILE and other.exists() and brand_of(TOKENS_FILE):
            name, ext = product_extension(json.loads(other.read_text()))
            if ext.get("prefix", name.rsplit(".", 1)[-1].lower()) == CSS:
                fail(f"the prefix '{CSS}' is {brand['name']}'s too; every brand needs its own")
    colours = TOKENS.get("color", {})
    for mode in [*NEUTRAL["modes"], *MODES]:
        if mode not in MODES:
            fail(f"the mode '{mode}' is not listed under $extensions.*.modes; every brand has {', '.join(NEUTRAL['modes'])}")
        if mode not in colours:
            fail(f"the mode '{mode}' is listed under $extensions.*.modes and has no colours under color.{mode}")
    light = [k for k in colours["light"] if not k.startswith("$")]
    for mode in MODES:
        have = [k for k in colours[mode] if not k.startswith("$")]
        missing, extra = [r for r in light if r not in have], [r for r in have if r not in light]
        if missing or extra:
            fail(f"color.{mode} " + " and ".join(
                p for p in (f"lacks {', '.join(missing)}" if missing else "", f"has {', '.join(extra)} that color.light lacks" if extra else "") if p))
    neutral_roles()
    for role in light:
        for platform in ("windows", "web"):
            system_colour(role, platform)
    name = EXT.get("notation")
    if not name:
        fail("no $extensions.*.notation: name the group that holds the notation metrics (Brasscribe's is score)")
    if not isinstance(TOKENS.get(name), dict):
        fail(f"$extensions.*.notation names the group '{name}', which the file does not have")
    display = EXT.get("fonts", {}).get("display")
    if not display or not display.get("faces"):
        fail("no $extensions.*.fonts.display with at least one face: the display type role needs its font")
    for key, font in EXT["fonts"].items():
        if key.startswith("$"):
            continue
        for field in ("family", "licence", "licence-name", "note", "faces"):
            if field not in font:
                fail(f"$extensions.*.fonts.{key} has no '{field}'")
        for face in font["faces"]:
            for field in ("file", "postscript", "weight", "style"):
                if field not in face:
                    fail(f"a face of $extensions.*.fonts.{key} has no '{field}'")
        for file in [font["licence"], *(face["file"] for face in font["faces"])]:
            if not (TOKENS_FILE.parent / file).is_file():
                fail(f"$extensions.*.fonts.{key} names {file}, which is not there")


# The accessibility palette (docs/accessibility/design-tokens.json) keeps its three themes;
# qa/reports/contrast-design-tokens.md checks every mode, high-contrast-light included.
A11Y_MODES = ("light", "dark", "high-contrast")


# ---------------------------------------------------------------- helpers

def roles() -> list[str]:
    return [k for k in TOKENS["color"]["light"] if not k.startswith("$")]


def hexval(mode: str, role: str) -> str:
    return TOKENS["color"][mode][role]["$value"]["hex"]


def alpha(mode: str, role: str) -> float:
    return TOKENS["color"][mode][role]["$value"].get("alpha", 1.0)


def desc(role: str) -> str:
    return TOKENS["color"]["light"][role].get("$description", "")


def camel(name: str) -> str:
    parts = re.split(r"[-_ ]", name)
    out = parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return ("n" + out) if out[:1].isdigit() else out


def pascal(name: str) -> str:
    c = camel(name)
    return c[:1].upper() + c[1:]


def upper_snake(name: str) -> str:
    return re.sub(r"[-\s]", "_", name).upper()


def dimension(tok: dict) -> float:
    return tok["$value"]["value"]


def fmt(v: float) -> str:
    return f"{v:g}"


def group(path: str) -> dict:
    node = TOKENS
    for p in path.split("."):
        node = node[p]
    return {k: v for k, v in node.items() if not k.startswith("$")}


def neutral_roles() -> dict[str, str]:
    """Each neutral role with the brand's token for it: its own name for the role, or the same name."""
    own = EXT.get("neutral", {}).get("roles", {})
    found = {}
    for name in NEUTRAL["roles"]:
        src = own.get(name, name)
        if src not in TOKENS["color"]["light"]:
            fail(f"no token for the neutral role '{name}'; add it or map it under $extensions.*.neutral.roles")
        found[name] = src
    return found


def system_colour(role: str, platform: str) -> str:
    """The system colour one of the brand's tokens takes in a Windows contrast theme ("windows") or under
    forced-colors ("web"), under the brand's own name: the one of the neutral role that reads it, or what
    the brand's tokens say under system-colours. They have to say it for a role of the brand's own, and for
    a token that two neutral roles with different system colours read (a link colour that is also brand
    text). Under a neutral name a role always takes the neutral role's system colour."""
    neutral = {NEUTRAL["roles"][name][platform] for name, src in neutral_roles().items() if src == role}
    own = EXT.get("system-colours", {}).get(role, {})
    if platform in own:
        return own[platform]
    if len(neutral) == 1:
        return neutral.pop()
    fail(f"no system colour ({platform}) for '{role}'; add it under $extensions.*.system-colours"
         + (" (the neutral roles that read it have different ones)" if neutral else ""))


def notation() -> tuple[str, dict]:
    """The brand's group of notation metrics and its name: Brasscribe's `score`, Fretscribe's `tab`."""
    name = EXT["notation"]
    return name, group(name)


def fonts(platform: str) -> list[tuple[str, dict, list[dict]]]:
    """The bundled faces: the font.family key, the font and its faces for a platform (apple, windows, web)."""
    found = []
    for key, font in EXT.get("fonts", {}).items():
        if not key.startswith("$"):
            found.append((key, font, [f for f in font["faces"] if platform in f.get("only", [platform])]))
    return found


def font_files(platform: str, folder: str) -> dict[str, bytes]:
    """The font files of a platform and their licence texts, under the names they have in the brand's folder."""
    out = {}
    base = TOKENS_FILE.parent
    for _, font, faces in fonts(platform):
        for face in faces:
            out[f"{folder}/{Path(face['file']).name}"] = (base / face["file"]).read_bytes()
        out[f"{folder}/{Path(font['licence']).name}"] = (base / font["licence"]).read_bytes()
    return out


def rgb_components(h: str) -> tuple[str, str, str]:
    return tuple(f"{int(h[i:i + 2], 16) / 255:.3f}" for i in (1, 3, 5))  # type: ignore[return-value]


def transform_path(d: str, s: float, tx: float, ty: float) -> str:
    """Scale then translate an SVG path (M L H V Q T C S Z, absolute and relative)."""
    toks = re.findall(r"[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?", d)
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "T": 2, "C": 6, "S": 4, "Z": 0}
    out, i, cmd = [], 0, "M"
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            out.append(t)
            i += 1
            if cmd in "Zz":
                continue
        n = arity[cmd.upper()]
        vals = [float(v) for v in toks[i:i + n]]
        i += n
        if cmd.isupper():
            if cmd == "H":
                vals = [vals[0] * s + tx]
            elif cmd == "V":
                vals = [vals[0] * s + ty]
            else:
                vals = [v * s + (tx if k % 2 == 0 else ty) for k, v in enumerate(vals)]
        else:
            vals = [v * s for v in vals]
        out.append(" ".join(f"{round(v, 3):g}" for v in vals))
    return " ".join(out)


def svg_path(file: Path) -> str:
    return " ".join(re.findall(r'<path[^>]*\sd="([^"]+)"', file.read_text()))


def icon_source(action: str, platform: str) -> tuple[str, str]:
    """Return ('system', name) or ('svg', path d on the 960 grid) for an action on a platform."""
    v = ICONS[action][platform]
    if isinstance(v, dict) and "custom" in v:
        return "svg", svg_path(BRAND / "icons" / "custom" / f"{v['custom']}.svg")
    if platform == "material":
        return "svg", svg_path(BRAND / "icons" / "material" / f"{v}.svg")
    return "system", v


# ---------------------------------------------------------------- accessibility compat file

def a11y_json() -> str:
    compat = EXT["a11yCompat"]
    keys = compat["keys"]
    pairs = [p for p in EXT["contrast"]["pairs"] if p[0] in keys and p[1] in keys]
    dist = [p for p in EXT["contrast"]["distinguish"] if p[0] in keys and p[1] in keys]
    data = {
        "$comment": ("Colour tokens for Play and Studio. Generated by design/tokens/build.py from "
                     "design/tokens/tokens.json, which is the source; edit that file. Checked by "
                     "qa/tools/contrast.py; the generated report is qa/reports/contrast-tokens.md. "
                     "Pairs list [foreground, background, minimum ratio, WCAG criterion]."),
        "themes": {m: {k: hexval(m, k) for k in keys} for m in A11Y_MODES},
        "pairs": pairs,
        "distinguish": dist,
        "legacy": {"$comment": "Colour used by the current engine output for SwiftF0-only notes; checked for reference.",
                   **compat["legacy"]},
    }
    # Same layout as the hand-written file: one pair per line.
    text = json.dumps(data, indent=2, ensure_ascii=False)
    for key in ("pairs", "distinguish"):
        rows = ",\n".join("    " + json.dumps(p, ensure_ascii=False).replace(",", ", ").replace(",  ", ", ") for p in data[key])
        block = json.dumps(data[key], indent=2, ensure_ascii=False).replace("\n", "\n  ")
        text = text.replace(f'"{key}": {block}', f'"{key}": [\n{rows}\n  ]')
    return text + "\n"


# ---------------------------------------------------------------- Apple

def apple_outputs() -> dict[str, str | bytes]:
    out: dict[str, str | bytes] = {}
    base = f"apple/{PRODUCT}Design.xcassets"
    info = {"info": {"author": "xcode", "version": 1}}
    out[f"{base}/Contents.json"] = json.dumps(info, indent=2) + "\n"
    out[f"{base}/{PRODUCT}/Contents.json"] = json.dumps(
        {"info": {"author": "xcode", "version": 1}, "properties": {"provides-namespace": True}}, indent=2) + "\n"

    def entry(mode: str, role: str, appearances: list[dict]) -> dict:
        r, g, b = rgb_components(hexval(mode, role))
        e = {"color": {"color-space": "srgb", "components": {
            "alpha": f"{alpha(mode, role):.3f}", "red": r, "green": g, "blue": b}}, "idiom": "universal"}
        if appearances:
            e["appearances"] = appearances
        return e

    dark = {"appearance": "luminosity", "value": "dark"}
    high = {"appearance": "contrast", "value": "high"}
    # The hidden Pink palette has its own namespace with the same high-contrast appearances, so Increase
    # Contrast still wins over it.
    palettes = [(PRODUCT, "light", "dark")]
    if PINK:
        out[f"{base}/{PRODUCT}Pink/Contents.json"] = out[f"{base}/{PRODUCT}/Contents.json"]
        palettes.append((f"{PRODUCT}Pink", "pink", "pink-dark"))
    for role in roles():
        for ns, light, dk in palettes:
            colors = [entry(light, role, []), entry(dk, role, [dark]),
                      entry("high-contrast", role, [high]), entry("high-contrast", role, [dark, high])]
            out[f"{base}/{ns}/{camel(role)}.colorset/Contents.json"] = json.dumps(
                {"colors": colors, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n"

    faces = {key: (font, found) for key, font, found in fonts("apple")}
    files = [f"Fonts/{Path(face['file']).name}" for _, found in faces.values() for face in found]
    lines = [f"// {HEADER}", "//", f"// Add {PRODUCT}Design.xcassets and {' and '.join(files)} to the same target",
             f"// as this file, and list the font{'s' if len(files) > 1 else ''} under UIAppFonts (iOS) / ATSApplicationFontsPath (macOS).", "",
             "import SwiftUI", "",
             f"public enum {PRODUCT}Design {{",
             "    private final class BundleToken {}",
             f"    /// The bundle that holds {PRODUCT}Design.xcassets: the package resources or the target this file is in.",
             "    public static let bundle: Bundle = {",
             "        #if SWIFT_PACKAGE",
             "        return Bundle.module",
             "        #else",
             "        return Bundle(for: BundleToken.self)",
             "        #endif",
             "    }()", ""]

    lines += ["    /// Spacing on the 4/8 grid, in points."]
    lines += ["    public enum Space {"]
    for k, v in group("space").items():
        lines.append(f"        public static let s{k}: CGFloat = {fmt(dimension(v))}")
    lines += ["    }", "", "    /// Corner radii, in points. `md` is the button shape on every platform.", "    public enum Radius {"]
    for k, v in group("radius").items():
        lines.append(f"        public static let {camel(k)}: CGFloat = {fmt(dimension(v))}")
    lines += ["    }", "", "    public enum Size {",
              f"        public static let touchMin: CGFloat = {fmt(dimension(TOKENS['size']['touch-min-apple']))}",
              f"        public static let iconSmall: CGFloat = {fmt(dimension(TOKENS['size']['icon-sm']))}",
              f"        public static let iconMedium: CGFloat = {fmt(dimension(TOKENS['size']['icon-md']))}",
              f"        public static let iconLarge: CGFloat = {fmt(dimension(TOKENS['size']['icon-lg']))}",
              f"        public static let contentMaxWidth: CGFloat = {fmt(dimension(TOKENS['size']['content-max']))}",
              f"        public static let sidebarWidth: CGFloat = {fmt(dimension(TOKENS['size']['sidebar']))}",
              "    }", ""]
    view, sc = notation()
    lines += [f"    /// {pascal(view)}-view metrics. Colours are in Color.{PRODUCT}.", f"    public enum {pascal(view)} {{"]
    for k in ("cursor-width", "focus-width", "focus-gap", "loop-edge-width", "selection-edge-width"):
        lines.append(f"        public static let {camel(k)}: CGFloat = {fmt(dimension(sc[k]))}")
    for k in ("zoom-min", "zoom-max", "zoom-step", "single-part-reflow-zoom", "mark-size-staff-spaces", "staff-height-min-phone-mm"):
        if k in sc:
            lines.append(f"        public static let {camel(k)}: Double = {fmt(sc[k]['$value'])}")
    lines += ["    }", ""]
    md = TOKENS["motion"]["duration"]
    ez = TOKENS["motion"]["easing"]
    lines += ["    /// Motion. Every animation goes through `animation(_:reduceMotion:)`.", "    public enum Motion {"]
    for k, v in md.items():
        lines.append(f"        public static let {camel(k)}: Double = {fmt(v['$value']['value'] / 1000)}")
    std = ez["standard"]["$value"]
    lines += [
        "",
        "        /// The standard curve, or a short cross-fade when Reduce Motion is on (nil for instant changes).",
        "        public static func animation(_ duration: Double = base, reduceMotion: Bool) -> Animation? {",
        "            if reduceMotion { return duration == 0 ? nil : .easeInOut(duration: min(duration, reduced)) }",
        f"            return .timingCurve({', '.join(fmt(x) for x in std)}, duration: duration)",
        "        }",
        "    }",
        "}", ""]

    if PINK:
        lines += [f"/// Which palette `Color.{PRODUCT}` reads: the standard one, or the hidden Pink one (design/system.md §10).",
                  "/// It is observable, so a view that reads a colour in `body` redraws when the palette changes. Light or",
                  "/// dark still follows the colour scheme, and Increase Contrast still gives the high-contrast colours.",
                  "@Observable",
                  f"public final class {PRODUCT}Palette: @unchecked Sendable {{",
                  f"    public static let shared = {PRODUCT}Palette()",
                  "    public var isPink = false",
                  "    public init() {}",
                  "}", ""]
        namespace = f'({PRODUCT}Palette.shared.isPink ? "{PRODUCT}Pink/" : "{PRODUCT}/")'
    else:
        namespace = f'"{PRODUCT}/"'
    lines += ["public extension Color {", "    /// Semantic colours with light, dark and high-contrast variants from the asset catalog.",
              f"    enum {PRODUCT} {{",
              "        private static func named(_ role: String) -> Color {",
              f"            Color({namespace} + role, bundle: {PRODUCT}Design.bundle)",
              "        }", ""]
    for role in roles():
        lines.append(f"        /// {desc(role)}")
        lines.append(f'        public static var {camel(role)}: Color {{ named("{camel(role)}") }}')
    lines += ["    }", "}", ""]

    typo = group("typography")
    weight = {400: "regular", 500: "medium", 600: "semibold", 700: "bold"}
    lines += ["public extension Font {", "    /// The type ramp, built on Dynamic Type text styles so it scales with the user's text size.",
              f"    enum {PRODUCT} {{"]
    for k, v in typo.items():
        plat = v.get("$extensions", {}).get("no.brasscribe.platform")
        if not plat:
            continue
        style = plat["apple"]["textStyle"]
        w = weight[v["$value"]["fontWeight"]]
        if "display" in v["$value"]["fontFamily"]:
            size = fmt(v["$value"]["fontSize"]["value"])
            expr = (f'.custom("{faces["display"][1][0]["postscript"]}", size: {size}, relativeTo: .{style})'
                    + ("" if w == "regular" else f".weight(.{w})"))
        else:
            expr = f".{style}" + ("" if w == "regular" else f".weight(.{w})")
            if k == "numeric":
                expr += ".monospacedDigit()"
        lines.append(f"        /// {v.get('$description', '')}")
        lines.append(f"        public static let {camel(k)}: Font = {expr}")
    for key, (font, found) in faces.items():
        if key != "display" and found:
            lines += ["", f"        /// {font['family']}. {font['note']}",
                      f"        public static func {camel(key)}(size: CGFloat) -> Font {{ .custom(\"{found[0]['postscript']}\", size: size) }}"]
    lines += ["    }", "}", ""]

    lines += ["/// One SF Symbol per action. The label is the visible text and the accessible name.",
              f"public enum {PRODUCT}Icon: CaseIterable, Sendable {{"]
    for a in ICONS:
        lines.append(f"    case {camel(a)}")
    lines += ["", "    public var systemName: String {", "        switch self {"]
    for a, v in ICONS.items():
        lines.append(f'        case .{camel(a)}: "{v["apple"]}"')
    lines += ["        }", "    }", "}", ""]

    lines += ["// The neutral names (design/tokens/README.md). Every brand's file declares them, so code that uses only",
              f"// these compiles against any brand. {PRODUCT}'s own roles and metrics are in the types above.", "",
              "public enum ScribeDesign {",
              f"    public static var bundle: Bundle {{ {PRODUCT}Design.bundle }}"]
    lines += [f"    public typealias {name} = {PRODUCT}Design.{name}" for name in ("Space", "Radius", "Size", "Motion")]
    lines += ["}", "", "public extension Color {", "    /// The colour roles every brand has.", "    enum Scribe {"]
    for name, src in neutral_roles().items():
        lines.append(f"        /// {desc(src)}")
        lines.append(f"        public static var {camel(name)}: Color {{ {PRODUCT}.{camel(src)} }}")
    lines += ["    }", "}", "",
              "public extension Font {", "    /// The type ramp every brand has.", "    enum Scribe {"]
    for k, v in typo.items():
        if v.get("$extensions", {}).get("no.brasscribe.platform"):
            lines.append(f"        /// {v.get('$description', '')}")
            lines.append(f"        public static var {camel(k)}: Font {{ {PRODUCT}.{camel(k)} }}")
    lines += ["    }", "}", ""]
    out[f"apple/{PRODUCT}Design.swift"] = "\n".join(lines)
    out.update(font_files("apple", "apple/Fonts"))
    return out


# ---------------------------------------------------------------- Android

def argb(h: str, a: float = 1.0) -> str:
    return f"0x{round(a * 255):02X}{h[1:].upper()}"


def android_source(kind: str, name: str, have) -> str:
    """The product's own name for a colour role, mode or token group of the Android API.

    $extensions.<product>.android.aliases maps the API's name to the product's, per kind:
    {"roles": {"brass": "brand"}, "modes": {"pink": "light"}, "groups": {"score": "tab"}}.
    A name the product neither has nor maps is an error, so the shared screens always compile.
    """
    src = ANDROID.get("aliases", {}).get(kind, {}).get(name, name)
    if src not in have:
        raise SystemExit(f"{rel(TOKENS_FILE)}: no {kind[:-1]} for '{name}' of the Android theme; "
                         f"add it or map it under $extensions.*.android.aliases.{kind}")
    return src


def android_color(mode: str, role: str) -> str:
    mode = android_source("modes", mode, TOKENS["color"])
    role = android_source("roles", role, TOKENS["color"][mode])
    return argb(hexval(mode, role), alpha(mode, role))


def android_group(name: str) -> dict:
    """A token group under the API's name. A key listed in android.inherit (as "score.zoom-min") that
    the product does not define keeps the default tokens' value."""
    own = group(android_source("groups", name, TOKENS))
    for path in ANDROID.get("inherit", []):
        g, _, key = path.partition(".")
        if g == name:
            own.setdefault(key, API[g][key])
    return own


def android_display_font() -> dict:
    """The display face in res/font: the file and its licence text (paths from the token file's folder
    when the product names its own) and the resource name."""
    font = ANDROID.get("display-font")
    if not font:
        return {"file": BRAND / "fonts" / "InstrumentSerif-Regular.ttf", "resource": "instrument_serif",
                "licence": BRAND / "fonts" / "OFL.txt"}
    base = TOKENS_FILE.parent
    return {"file": base / font["file"], "resource": font["resource"], "licence": base / font["licence"]}


def android_outputs() -> dict[str, str | bytes]:
    out: dict[str, str | bytes] = {}
    pkg = "no.brasscribe.design"
    rs = [k for k in API["color"]["light"] if not k.startswith("$")]
    font = android_display_font()
    dist = rel(DIST)

    def role_desc(r: str) -> str:
        src = android_source("roles", r, TOKENS["color"]["light"])
        return desc(src) if src == r else f"{PRODUCT}'s `{src}`. {desc(src)}"
    L = [f"// {HEADER}", f"package {pkg}", "",
         "import android.app.UiModeManager",
         "import android.os.Build",
         "import androidx.compose.animation.core.CubicBezierEasing",
         "import androidx.compose.foundation.isSystemInDarkTheme",
         "import androidx.compose.foundation.shape.RoundedCornerShape",
         "import androidx.compose.material3.ColorScheme",
         "import androidx.compose.material3.MaterialTheme",
         "import androidx.compose.material3.Shapes",
         "import androidx.compose.material3.Typography",
         "import androidx.compose.material3.darkColorScheme",
         "import androidx.compose.material3.lightColorScheme",
         "import androidx.compose.runtime.Composable",
         "import androidx.compose.runtime.CompositionLocalProvider",
         "import androidx.compose.runtime.Immutable",
         "import androidx.compose.runtime.ReadOnlyComposable",
         "import androidx.compose.runtime.staticCompositionLocalOf",
         "import androidx.compose.ui.graphics.Color",
         "import androidx.compose.ui.platform.LocalContext",
         "import androidx.compose.ui.text.TextStyle",
         "import androidx.compose.ui.text.font.FontFamily",
         "import androidx.compose.ui.text.font.FontWeight",
         "import androidx.compose.ui.text.style.TextAlign",
         "import androidx.compose.ui.unit.dp",
         "import androidx.compose.ui.unit.sp", "",
         "/** Semantic colours. Material components read [ColorScheme]; the score view reads these directly. */",
         "@Immutable",
         "data class BrasscribeColors("]
    for r in rs:
        L.append(f"    /** {role_desc(r)} */")
        L.append(f"    val {camel(r)}: Color,")
    L += ["    val isHighContrast: Boolean,", ")", ""]
    for mode, name in (("light", "BrasscribeLightColors"), ("dark", "BrasscribeDarkColors"),
                       ("high-contrast", "BrasscribeHighContrastColors"), ("high-contrast-light", "BrasscribeHighContrastLightColors"),
                       ("pink", "BrasscribePinkColors"), ("pink-dark", "BrasscribePinkDarkColors")):
        if mode == "high-contrast-light":
            L.append("/** High contrast on a light ground. Not yet chosen by [BrasscribeTheme], which uses the dark one. */")
        if mode == "pink" and android_source("modes", mode, TOKENS["color"]) != mode:
            L.append(f"/** {PRODUCT} has no Pink palette: `pink = true` in [BrasscribeTheme] gives its standard colours. */")
        elif mode == "pink":
            L.append("/** The hidden Pink palette (design/system.md §10), chosen by [BrasscribeTheme] with `pink = true`. */")
        L.append(f"val {name} = BrasscribeColors(")
        for r in rs:
            L.append(f"    {camel(r)} = Color({android_color(mode, r)}),")
        L += [f"    isHighContrast = {'true' if mode.startswith('high-contrast') else 'false'},", ")", ""]

    L += [f"/** Maps the semantic roles onto Material 3 so stock components look like {PRODUCT}. */",
          "fun BrasscribeColors.toColorScheme(dark: Boolean): ColorScheme {",
          "    val scheme = if (dark) darkColorScheme() else lightColorScheme()",
          "    return scheme.copy(",
          "        primary = primary, onPrimary = onPrimary,",
          "        primaryContainer = secondary, onPrimaryContainer = onSecondary, inversePrimary = brass,",
          "        secondary = text, onSecondary = bg,",
          "        secondaryContainer = secondary, onSecondaryContainer = onSecondary,",
          "        tertiary = brassText, onTertiary = onPrimary,",
          "        tertiaryContainer = brassTint, onTertiaryContainer = text,",
          "        background = bg, onBackground = text,",
          "        surface = bg, onSurface = text, surfaceVariant = surface, onSurfaceVariant = textMuted,",
          "        surfaceTint = bg, inverseSurface = text, inverseOnSurface = bg,",
          "        error = error, onError = bg, errorContainer = surface, onErrorContainer = error,",
          "        outline = borderStrong, outlineVariant = border, scrim = Color.Black,",
          "        surfaceBright = surfaceRaised, surfaceDim = surface,",
          "        surfaceContainerLowest = surfaceRaised, surfaceContainerLow = surfaceRaised,",
          "        surfaceContainer = surface, surfaceContainerHigh = surfaceRaised, surfaceContainerHighest = secondary,",
          "    )",
          "}", ""]

    typo = group("typography")
    weight = {400: "Normal", 500: "Medium", 600: "SemiBold", 700: "Bold"}
    L += ["/** The type ramp as Material 3 roles. Sizes are sp, so they follow the system font scale. */",
          "fun brasscribeTypography(display: FontFamily = FontFamily.Serif): Typography {",
          "    val base = Typography()", "    return base.copy("]
    used = {}
    for k, v in typo.items():
        plat = v.get("$extensions", {}).get("no.brasscribe.platform")
        if not plat or k == "numeric":
            continue
        m = plat["material"]
        used[m["role"]] = (k, v, m)
    for role, (k, v, m) in used.items():
        fam = "display" if "display" in v["$value"]["fontFamily"] else "FontFamily.Default"
        ls = v["$value"]["letterSpacing"]["value"]
        L.append(f"        {role} = base.{role}.copy(fontFamily = {fam}, fontWeight = FontWeight.{weight[v['$value']['fontWeight']]}, "
                 f"fontSize = {fmt(m['sizeSp'])}.sp, lineHeight = {fmt(m['lineHeightSp'])}.sp, letterSpacing = {fmt(ls)}.sp),")
    L += ["    )", "}", ""]
    num = typo["numeric"]["$extensions"]["no.brasscribe.platform"]["material"]
    L += ["/** Bar/beat, speed and tempo readouts: tabular figures so the numbers don't jiggle. */",
          f"val BrasscribeNumericStyle = TextStyle(fontWeight = FontWeight.Medium, fontSize = {num['sizeSp']}.sp, "
          f"lineHeight = {num['lineHeightSp']}.sp, fontFeatureSettings = \"tnum\", textAlign = TextAlign.Start)", ""]

    rad = group("radius")
    L += ["val BrasscribeShapes = Shapes(",
          f"    extraSmall = RoundedCornerShape({fmt(dimension(rad['xs']))}.dp),",
          f"    small = RoundedCornerShape({fmt(dimension(rad['sm']))}.dp),",
          f"    medium = RoundedCornerShape({fmt(dimension(rad['md']))}.dp),",
          f"    large = RoundedCornerShape({fmt(dimension(rad['lg']))}.dp),",
          f"    extraLarge = RoundedCornerShape({fmt(dimension(rad['xl']))}.dp),",
          ")", "",
          "/** The brand's one button shape. Material buttons default to a pill; pass this instead. */",
          f"val BrasscribeButtonShape = RoundedCornerShape({fmt(dimension(rad['md']))}.dp)", ""]

    L += ["object BrasscribeSpace {"]
    for k, v in group("space").items():
        L.append(f"    val s{k} = {fmt(dimension(v))}.dp")
    L += ["}", "", "object BrasscribeSize {",
          f"    val touchMin = {fmt(dimension(TOKENS['size']['touch-min-android']))}.dp",
          f"    val iconMedium = {fmt(dimension(TOKENS['size']['icon-md']))}.dp",
          f"    val iconLarge = {fmt(dimension(TOKENS['size']['icon-lg']))}.dp",
          f"    val contentMaxWidth = {fmt(dimension(TOKENS['size']['content-max']))}.dp",
          f"    val sidebarWidth = {fmt(dimension(TOKENS['size']['sidebar']))}.dp",
          "}", ""]
    sc = android_group("score")
    L += ["object BrasscribeScore {"]
    for k in ("cursor-width", "focus-width", "focus-gap", "loop-edge-width", "selection-edge-width"):
        L.append(f"    val {camel(k)} = {fmt(dimension(sc[k]))}.dp")
    for k in ("zoom-min", "zoom-max", "zoom-step", "single-part-reflow-zoom"):
        L.append(f"    const val {camel(k)} = {int(sc[k]['$value'])}")
    L += ["}", ""]
    L += ["/** Durations in ms. With animations off (ANIMATOR_DURATION_SCALE 0) use [reduced] cross-fades or none. */",
          "object BrasscribeMotion {"]
    for k, v in TOKENS["motion"]["duration"].items():
        L.append(f"    const val {camel(k)} = {v['$value']['value']}")
    for k, v in TOKENS["motion"]["easing"].items():
        L.append(f"    val {camel(k)}Easing = CubicBezierEasing({', '.join(fmt(x) + 'f' for x in v['$value'])})")
    L += ["}", ""]

    L += ["val LocalBrasscribeColors = staticCompositionLocalOf { BrasscribeLightColors }", "",
          "/** Android 14+ reports the system contrast level; 0.5 and above is treated as high contrast. */",
          "@Composable",
          "fun systemHighContrast(): Boolean {",
          "    val context = LocalContext.current",
          "    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return false",
          "    val ui = context.getSystemService(UiModeManager::class.java) ?: return false",
          "    return ui.contrast >= 0.5f",
          "}", "",
          "/**",
          f" * {PRODUCT} on Material 3. Dynamic colour is deliberately not used: the score palette is",
          " * fixed for accessibility and the brand stays the same on every device.",
          " *",
          f" * @param display the brand display face; pass FontFamily(Font(R.font.{font['resource']})) after copying",
          f" *   {dist}/android/res/font into the app. Defaults to the system serif.",
          " * @param pink the hidden Pink palette, light or dark by [dark]. The system's high contrast still wins.",
          " */",
          "@Composable",
          "fun BrasscribeTheme(",
          "    dark: Boolean = isSystemInDarkTheme(),",
          "    highContrast: Boolean = systemHighContrast(),",
          "    pink: Boolean = false,",
          "    display: FontFamily = FontFamily.Serif,",
          "    content: @Composable () -> Unit,",
          ") {",
          "    val colors = when {",
          "        highContrast -> BrasscribeHighContrastColors",
          "        pink && dark -> BrasscribePinkDarkColors",
          "        pink -> BrasscribePinkColors",
          "        dark -> BrasscribeDarkColors",
          "        else -> BrasscribeLightColors",
          "    }",
          "    CompositionLocalProvider(LocalBrasscribeColors provides colors) {",
          "        MaterialTheme(",
          "            colorScheme = colors.toColorScheme(dark = dark || highContrast),",
          "            typography = brasscribeTypography(display),",
          "            shapes = BrasscribeShapes,",
          "            content = content,",
          "        )",
          "    }",
          "}", "",
          "object BrasscribeTheme {",
          "    val colors: BrasscribeColors",
          "        @Composable @ReadOnlyComposable get() = LocalBrasscribeColors.current",
          "}", ""]
    out["android/kotlin/no/brasscribe/design/BrasscribeTheme.kt"] = "\n".join(L)

    I = [f"// {HEADER}", f"package {pkg}", "",
         "/**",
         f" * One icon per action. Copy {dist}/android/res/drawable/ic_bc_*.xml into the app and use",
         " * painterResource(R.drawable.<drawable>). [material] names the Material Symbols Rounded source",
         " * (or \"custom\"). The label string is the accessible name; see icons.json for en and nb.",
         " */",
         "enum class BrasscribeIcon(val drawable: String, val material: String) {"]
    for a, v in ICONS.items():
        m = v["material"]
        src = m if isinstance(m, str) else "custom:" + m["custom"]
        I.append(f'    {upper_snake(a)}("ic_bc_{a.replace("-", "_")}", "{src}"),')
    I += ["}", ""]
    out["android/kotlin/no/brasscribe/design/BrasscribeIcon.kt"] = "\n".join(I)
    out["android/kotlin/no/brasscribe/design/ScribeTheme.kt"] = android_neutral(pkg)

    for a in ICONS:
        _, d = icon_source(a, "material")
        out[f"android/res/drawable/ic_bc_{a.replace('-', '_')}.xml"] = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f"<!-- {HEADER} -->\n"
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="24dp" android:height="24dp"\n'
            '    android:viewportWidth="960" android:viewportHeight="960">\n'
            '    <group android:translateY="960">\n'
            f'        <path android:fillColor="#FF000000" android:pathData="{d}"/>\n'
            "    </group>\n</vector>\n")
    out[f"android/res/font/{font['resource']}.ttf"] = font["file"].read_bytes()
    out["android/res/font/OFL.txt"] = font["licence"].read_bytes()
    return out


def android_neutral(pkg: str) -> str:
    """The neutral names of the Android theme: other names for the declarations of BrasscribeTheme.kt, which
    every brand's theme has today. A neutral role that BrasscribeColors names differently gets a property."""
    api = {name: (API["$extensions"]["no.brasscribe"]["neutral"]["roles"].get(name, name)) for name in NEUTRAL["roles"]}
    S = [f"// {HEADER}", f"package {pkg}", "",
         "import androidx.compose.foundation.isSystemInDarkTheme",
         "import androidx.compose.foundation.shape.RoundedCornerShape",
         "import androidx.compose.material3.Shapes",
         "import androidx.compose.material3.Typography",
         "import androidx.compose.runtime.Composable",
         "import androidx.compose.runtime.ProvidableCompositionLocal",
         "import androidx.compose.runtime.ReadOnlyComposable",
         "import androidx.compose.ui.graphics.Color",
         "import androidx.compose.ui.text.TextStyle",
         "import androidx.compose.ui.text.font.FontFamily", "",
         "/*",
         " * The neutral names (design/tokens/README.md). Every brand's theme declares them, so screens that use only",
         f" * these compile against any brand. They are other names for the declarations in BrasscribeTheme.kt, which",
         f" * holds {PRODUCT}'s values; a brand's own roles are read from there.",
         " */", "",
         "/** The colour roles every brand has (and, until the themes are split, the brand's own beside them). */",
         "typealias ScribeColors = BrasscribeColors", ""]
    for name, src in api.items():
        if src != name:
            own = android_source("roles", src, TOKENS["color"]["light"])
            S += [f"/** {desc(own)} */", f"val ScribeColors.{camel(name)}: Color get() = {camel(src)}", ""]
    for mode, name in (("light", "Light"), ("dark", "Dark"), ("high-contrast", "HighContrast"), ("high-contrast-light", "HighContrastLight")):
        assert mode in NEUTRAL["modes"]
        S.append(f"val Scribe{name}Colors: ScribeColors get() = Brasscribe{name}Colors")
    S += ["",
          "val LocalScribeColors: ProvidableCompositionLocal<ScribeColors> get() = LocalBrasscribeColors", "",
          "/** The type ramp as Material 3 roles. */",
          "fun scribeTypography(display: FontFamily = FontFamily.Serif): Typography = brasscribeTypography(display)", "",
          "val ScribeNumericStyle: TextStyle get() = BrasscribeNumericStyle",
          "val ScribeShapes: Shapes get() = BrasscribeShapes",
          "val ScribeButtonShape: RoundedCornerShape get() = BrasscribeButtonShape", "",
          "typealias ScribeSpace = BrasscribeSpace",
          "typealias ScribeSize = BrasscribeSize",
          "typealias ScribeMotion = BrasscribeMotion", "",
          f"/** {PRODUCT} on Material 3: light or dark by [dark], and the high-contrast colours when the system asks. */",
          "@Composable",
          "fun ScribeTheme(",
          "    dark: Boolean = isSystemInDarkTheme(),",
          "    highContrast: Boolean = systemHighContrast(),",
          "    display: FontFamily = FontFamily.Serif,",
          "    content: @Composable () -> Unit,",
          ") = BrasscribeTheme(dark = dark, highContrast = highContrast, display = display, content = content)", "",
          "object ScribeTheme {",
          "    val colors: ScribeColors",
          "        @Composable @ReadOnlyComposable get() = LocalBrasscribeColors.current",
          "}", ""]
    return "\n".join(S)


# ---------------------------------------------------------------- Windows

def windows_theme_dictionaries(light: str, dark: str) -> list[str]:
    """The Light, Dark and HighContrast theme dictionaries of every colour role, for two modes of tokens.json."""
    # Every role under the brand's prefix, then the neutral roles under theirs. The neutral keys carry the
    # values themselves: a key that pointed at the brand's would not follow a palette merged later (Pink).
    names = [(KEY + pascal(r), r) for r in roles()]
    neutral = [("Scribe" + pascal(name), src) for name, src in neutral_roles().items()]
    X = ["    <ResourceDictionary.ThemeDictionaries>"]
    for mode, key in ((light, "Light"), (dark, "Dark")):
        X.append(f'        <ResourceDictionary x:Key="{key}">')
        for part in (names, neutral):
            for k, r in part:
                X.append(f'            <Color x:Key="{k}Color">#{round(alpha(mode, r) * 255):02X}{hexval(mode, r)[1:]}</Color>')
            for k, r in part:
                X.append(f'            <SolidColorBrush x:Key="{k}Brush" Color="{{StaticResource {k}Color}}"/>')
        X.append("        </ResourceDictionary>")
    X.append('        <ResourceDictionary x:Key="HighContrast">')
    system = [(k, system_colour(r, "windows")) for k, r in names]
    for part in (system, [("Scribe" + pascal(name), NEUTRAL["roles"][name]["windows"]) for name in neutral_roles()]):
        for k, colour in part:
            X.append(f'            <StaticResource x:Key="{k}Color" ResourceKey="{colour}"/>')
        for k, colour in part:
            X.append(f'            <SolidColorBrush x:Key="{k}Brush" Color="{{ThemeResource {colour}}}"/>')
    X += ["        </ResourceDictionary>", "    </ResourceDictionary.ThemeDictionaries>"]
    return X


XAML_OPEN = ['<ResourceDictionary',
             '    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"',
             '    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">']


def windows_pink() -> str:
    """The hidden Pink palette (design/system.md §10): the colour roles only, merged after the brand's theme."""
    X = ['<?xml version="1.0" encoding="utf-8"?>', f"<!-- {HEADER} -->",
         f"<!-- The hidden Pink palette (design/system.md §10). Merged after {PRODUCT}Theme.xaml while Pink is chosen, so its",
         "     colour roles win; Light and Dark follow the system. Contrast themes still map every role to the system's colours. -->"]
    X += XAML_OPEN + windows_theme_dictionaries("pink", "pink-dark") + ["</ResourceDictionary>", ""]
    return "\n".join(X)


def windows_outputs() -> dict[str, str | bytes]:
    X = ['<?xml version="1.0" encoding="utf-8"?>', f"<!-- {HEADER} -->",
         f"<!-- Merge into App.xaml: <ResourceDictionary Source=\"ms-appx:///Themes/{PRODUCT}Theme.xaml\"/>.",
         f"     Use {{ThemeResource {KEY}TextBrush}} etc. Contrast themes map every role to the user's system colours. -->"]
    X += XAML_OPEN + windows_theme_dictionaries("light", "dark") + [""]
    B = ["    <!-- Spacing (epx), radii, sizes -->"]
    for k, v in group("space").items():
        B.append(f'    <x:Double x:Key="{KEY}Space{k}">{fmt(dimension(v))}</x:Double>')
        B.append(f'    <Thickness x:Key="{KEY}Padding{k}">{fmt(dimension(v))}</Thickness>')
    for k, v in group("radius").items():
        B.append(f'    <CornerRadius x:Key="{KEY}Radius{pascal(k)}">{fmt(dimension(v))}</CornerRadius>')
    B.append(f'    <x:Double x:Key="{KEY}TouchMin">{fmt(dimension(TOKENS["size"]["touch-min-windows"]))}</x:Double>')
    B.append(f'    <x:Double x:Key="{KEY}ContentMaxWidth">{fmt(dimension(TOKENS["size"]["content-max"]))}</x:Double>')
    B.append(f'    <x:Double x:Key="{KEY}SidebarWidth">{fmt(dimension(TOKENS["size"]["sidebar"]))}</x:Double>')
    view, sc = notation()
    # The start of each key that is the brand's own, with no neutral name: its notation metrics, and the
    # icons, whose actions (icons.json) are one product's so far.
    own = [f"{KEY}{pascal(view)}", f"{KEY}Icon"]
    for k in ("cursor-width", "focus-width", "focus-gap", "loop-edge-width", "selection-edge-width"):
        B.append(f'    <x:Double x:Key="{KEY}{pascal(view)}{pascal(k)}">{fmt(dimension(sc[k]))}</x:Double>')
    B += ["", "    <!-- Motion (ms); check UISettings.AnimationsEnabled and fall back to BcDurationReduced cross-fades -->".replace("Bc", KEY)]
    for k, v in TOKENS["motion"]["duration"].items():
        B.append(f'    <x:Double x:Key="{KEY}Duration{pascal(k)}">{v["$value"]["value"]}</x:Double>')
    B += ["", "    <!-- Type ramp: each style is based on the WinUI ramp style it maps to -->"]
    for key, font, faces in fonts("windows"):
        if faces:
            B.append(f'    <FontFamily x:Key="{KEY}{pascal(key)}FontFamily">ms-appx:///Assets/Fonts/{Path(faces[0]["file"]).name}#{font["family"]}</FontFamily>')
            if key != "display":
                own.append(f"{KEY}{pascal(key)}FontFamily")
    weight = {400: "Normal", 500: "Medium", 600: "SemiBold", 700: "Bold"}
    for k, v in group("typography").items():
        plat = v.get("$extensions", {}).get("no.brasscribe.platform")
        if not plat:
            continue
        w = plat["windows"]
        B.append(f'    <Style x:Key="{KEY}{pascal(k)}TextBlockStyle" TargetType="TextBlock" BasedOn="{{StaticResource {w["style"]}TextBlockStyle}}">')
        if "display" in v["$value"]["fontFamily"]:
            B.append(f'        <Setter Property="FontFamily" Value="{{StaticResource {KEY}DisplayFontFamily}}"/>')
        B.append(f'        <Setter Property="FontWeight" Value="{weight[v["$value"]["fontWeight"]]}"/>')
        B.append(f'        <Setter Property="FontSize" Value="{fmt(w["sizeEpx"])}"/>')
        B.append(f'        <Setter Property="LineHeight" Value="{fmt(w["lineHeightEpx"])}"/>')
        B.append('        <Setter Property="TextWrapping" Value="Wrap"/>')
        B.append("    </Style>")
    B += ["", "    <!-- Icons: Segoe Fluent Icons glyphs for FontIcon.Glyph; custom glyphs as 20 epx path data for PathIcon -->"]
    for a in ICONS:
        kind, v = icon_source(a, "windows")
        if kind == "system":
            B.append(f'    <x:String x:Key="{KEY}Icon{pascal(a)}">&#x{v["glyph"]};</x:String>')
        else:
            B.append(f'    <x:String x:Key="{KEY}IconPath{pascal(a)}">{transform_path(v, 20 / 960, 0, 20)}</x:String>')
    X += B
    # The same resources under the neutral names, values and all (see windows_theme_dictionaries).
    X += ["", "    <!-- The neutral names (design/tokens/README.md): the same keys in every brand's theme. The brand's own",
          "         resources have the keys above only. -->"]
    named = re.compile(rf'(x:Key="|\{{StaticResource ){KEY}(?=[A-Z0-9])')
    for line in B:
        if "<!--" in line or not line or any(f'x:Key="{start}' in line for start in own):
            continue
        X.append(named.sub(r"\1Scribe", line))
    X += ["</ResourceDictionary>", ""]
    out: dict[str, str | bytes] = {f"windows/{PRODUCT}Theme.xaml": "\n".join(X)}
    if PINK:
        out[f"windows/{PRODUCT}PinkTheme.xaml"] = windows_pink()
    out.update(font_files("windows", "windows/Assets/Fonts"))
    return out


# ---------------------------------------------------------------- Web (Studio)

def css_color(mode: str, r: str) -> str:
    a = alpha(mode, r)
    h = hexval(mode, r)
    return h if a == 1 else f"rgb({int(h[1:3], 16)} {int(h[3:5], 16)} {int(h[5:7], 16)} / {fmt(a)})"


def web_outputs() -> dict[str, str | bytes]:
    """The style sheets are written with Brasscribe's prefix (--bc-); `own` gives another brand its own."""
    rs = roles()
    view, sc = notation()

    def own(lines: list[str]) -> str:
        return "\n".join(lines).replace("--bc-", f"--{CSS}-")

    def block(mode: str, indent: str) -> list[str]:
        return [f"{indent}--bc-{r}: {css_color(mode, r)};" for r in rs]

    C = [f"/* {HEADER} */", "/* Import fonts.css too if the page uses the display face. */", "",
         ":root {", "  color-scheme: light;"]
    C += block("light", "  ")
    fam = TOKENS["font"]["family"]
    quote = lambda xs: ", ".join(f'"{x}"' if " " in x else x for x in xs)
    C += [f"  --bc-font-text: {quote(['system-ui', '-apple-system', 'Segoe UI Variable Text', 'Segoe UI', 'Roboto', 'sans-serif'])};",
          f"  --bc-font-display: {quote(fam['display']['$value'])};",
          f"  --bc-font-mono: {quote(['ui-monospace', 'SF Mono', 'Cascadia Mono', 'Roboto Mono', 'Menlo', 'monospace'])};"]
    extra_fonts = [k for k in fam if not k.startswith("$") and k not in ("text", "display", "mono")]
    C += [f"  --bc-font-{k}: {quote(fam[k]['$value'])};" for k in extra_fonts]
    for k, v in group("typography").items():
        val = v["$value"]
        C.append(f"  --bc-type-{k}-size: {fmt(val['fontSize']['value'] / 16)}rem;")
        C.append(f"  --bc-type-{k}-line: {fmt(val['lineHeight'])};")
        C.append(f"  --bc-type-{k}-weight: {val['fontWeight']};")
    for k, v in group("space").items():
        C.append(f"  --bc-space-{k}: {fmt(dimension(v) / 16)}rem;")
    for k, v in group("radius").items():
        C.append(f"  --bc-radius-{k}: {fmt(dimension(v))}px;")
    for k, v in TOKENS["elevation"].items():
        if k.startswith("$"):
            continue
        sh = v["$value"]
        def shadow_color(c: dict) -> str:
            h = c["hex"]
            return f"rgb({int(h[1:3], 16)} {int(h[3:5], 16)} {int(h[5:7], 16)} / {fmt(c.get('alpha', 1))})"
        val = "none" if not sh else ", ".join(
            f"{fmt(s['offsetX']['value'])}px {fmt(s['offsetY']['value'])}px {fmt(s['blur']['value'])}px {fmt(s['spread']['value'])}px {shadow_color(s['color'])}" for s in sh)
        C.append(f"  --bc-elevation-{k}: {val};")
    for k, v in TOKENS["motion"]["duration"].items():
        C.append(f"  --bc-duration-{k}: {v['$value']['value']}ms;")
    for k, v in TOKENS["motion"]["easing"].items():
        C.append(f"  --bc-ease-{k}: cubic-bezier({', '.join(fmt(x) for x in v['$value'])});")
    for k in ("cursor-width", "focus-width", "focus-gap", "loop-edge-width", "selection-edge-width"):
        C.append(f"  --bc-{view}-{k}: {fmt(dimension(sc[k]))}px;")
    C.append(f"  --bc-touch-min: {fmt(dimension(TOKENS['size']['touch-min-web']) / 16)}rem;")
    C.append(f"  --bc-control-min: {fmt(dimension(TOKENS['size']['control-min-web']) / 16)}rem;")
    C.append(f"  --bc-target-gap: {fmt(dimension(TOKENS['size']['target-gap-web']) / 16)}rem;")
    C.append(f"  --bc-content-max: {fmt(dimension(TOKENS['size']['content-max']) / 16)}rem;")
    C += ["}", "",
          "/* Dark: follow the system unless the page pins a theme with data-theme. */",
          "@media (prefers-color-scheme: dark) {", '  :root:not([data-theme="light"]) {', "    color-scheme: dark;"]
    C += block("dark", "    ")
    C += ["    --bc-elevation-1: none;", "    --bc-elevation-2: 0 4px 16px rgb(0 0 0 / 0.5);", "    --bc-elevation-3: 0 12px 32px rgb(0 0 0 / 0.6);",
          "  }", "}", ':root[data-theme="dark"] {', "  color-scheme: dark;"]
    C += block("dark", "  ")
    C += ["  --bc-elevation-1: none;", "  --bc-elevation-2: 0 4px 16px rgb(0 0 0 / 0.5);", "  --bc-elevation-3: 0 12px 32px rgb(0 0 0 / 0.6);", "}", ""]
    if PINK:
        C += ["/* Pink, the hidden palette (design/system.md §10): data-palette=\"pink\" on the root. Light or dark",
              "   follows data-theme when the page pins one, else the system. More contrast and forced colours win. */",
              "@media (forced-colors: none) and (not (prefers-contrast: more)) {",
              '  :root[data-palette="pink"] {', "    color-scheme: light;"]
        C += block("pink", "    ")
        C += ["  }", '  :root[data-palette="pink"][data-theme="dark"] {', "    color-scheme: dark;"]
        C += block("pink-dark", "    ")
        C += ["  }", "}",
              "@media (forced-colors: none) and (not (prefers-contrast: more)) and (prefers-color-scheme: dark) {",
              '  :root[data-palette="pink"]:not([data-theme="light"]) {', "    color-scheme: dark;"]
        C += block("pink-dark", "    ")
        C += ["  }", "}", ""]
    C += ["/* High contrast: our palettes when the user asks for more contrast; tints become outlines.",
          "   Light or dark follows the resolved theme: data-theme when the page pins one, else the system.",
          "   Under forced colours the system colours below win instead. */"]
    more = "@media (prefers-contrast: more) and (forced-colors: none)"
    no_shadow = ["--bc-elevation-1: none;", "--bc-elevation-2: none;", "--bc-elevation-3: none;"]

    def hc(selector: str, mode: str, media: str | None) -> list[str]:
        scheme = "light" if mode == "high-contrast-light" else "dark"
        ind = "    " if media else "  "
        body = [f"{ind[:-2]}{selector} {{", f"{ind}color-scheme: {scheme};", *block(mode, ind), *(ind + s for s in no_shadow), f"{ind[:-2]}}}"]
        return [f"{media} {{", *body, "}"] if media else body

    C += hc(':root:not([data-theme="dark"])', "high-contrast-light", more)
    C += hc(':root:not([data-theme="light"])', "high-contrast", f"{more} and (prefers-color-scheme: dark)")
    C += hc(':root[data-theme="dark"]', "high-contrast", more)
    C += hc(':root[data-theme="high-contrast"]', "high-contrast", None)
    C += hc(':root[data-theme="high-contrast-light"]', "high-contrast-light", None)
    C += ["",
          "/* Forced colours (Windows contrast themes): system colours only; shape carries the meaning. */",
          "@media (forced-colors: active) {", "  :root {"]
    C += [f"    --bc-{r}: {system_colour(r, 'web')};" for r in rs]
    C += ["    --bc-elevation-1: none;", "    --bc-elevation-2: none;", "    --bc-elevation-3: none;", "  }", "}", "",
          "/* Reduced motion: no movement; state changes cross-fade at most --bc-duration-reduced. */",
          "@media (prefers-reduced-motion: reduce) {", "  :root {",
          "    --bc-duration-fast: 0ms;", "    --bc-duration-base: var(--bc-duration-reduced);", "    --bc-duration-slow: var(--bc-duration-reduced);",
          "  }", "}", ""]

    # The neutral names: one for every variable of the first block that is not the brand's own. var() is
    # resolved where it is used, so each follows the brand's value in every mode and palette.
    # A type role with no native text style on the other platforms (Studio's) is the brand's own.
    own_type = [k for k, v in group("typography").items() if "no.brasscribe.platform" not in v.get("$extensions", {})]
    C += ["/* The neutral names (design/tokens/README.md): the same in every brand's file, so styles that use only",
          "   these work with any brand. Each follows the value above in every mode. */", ":root {"]
    C += [f"  --scribe-{name}: var(--bc-{src});" for name, src in neutral_roles().items()]
    for line in C[C.index(":root {") + 1:C.index("}")]:
        name = line.strip().removeprefix("--bc-").split(":")[0]
        if not line.startswith("  --bc-") or name in rs or name.startswith(f"{view}-") or name in (f"font-{k}" for k in extra_fonts):
            continue
        if any(name.startswith(f"type-{k}-") for k in own_type):
            continue
        C.append(f"  --scribe-{name}: var(--bc-{name});")
    C += ["}", ""]

    F = [f"/* {HEADER} */"]
    for _, font, faces in fonts("web"):
        F.append(f"/* {font['family']}, {font['licence-name']} (fonts/{Path(font['licence']).name}). {font['note']} */")
        for face in faces:
            F += ["@font-face {", f'  font-family: "{font["family"]}";', f'  src: url("fonts/{Path(face["file"]).name}") format("truetype");',
                  f"  font-weight: {face['weight']};", f"  font-style: {face['style']};", "  font-display: swap;", "}"]
    F.append("")

    compat = {"bg": "bg", "surface": "surface", "text": "text", "text-muted": "text-muted", "ink": "ink", "staff": "staff",
              "uncertain": "uncertain", "very-uncertain": "very-uncertain", "adlib-tint": "adlib-tint", "loop-tint": "loop-tint",
              "loop-edge": "loop-edge", "cursor": "cursor", "focus": "focus", "error": "error", "ok": "success",
              "border": "border-strong", "m1": "model-1", "m2": "model-2", "m3": "model-3", "m4": "model-4"}
    S = [f"/* {HEADER} */", f"/* Maps the variable names in studio/src/styles.css onto the {PRODUCT} tokens.",
         f"   Load after {PRODUCT.lower()}.css and instead of Studio's own colour blocks. */", ":root {"]
    S += [f"  --{k}: var(--bc-{v});" for k, v in compat.items()]
    S += ["  --space: var(--bc-space-4);", "  font-family: var(--bc-font-text);", "}", ""]

    out: dict[str, str | bytes] = {f"web/{PRODUCT.lower()}.css": own(C), "web/fonts.css": "\n".join(F)}
    if EXT.get("web", {}).get("studio-compat"):
        out["web/studio-compat.css"] = own(S)
    out.update(font_files("web", "web/fonts"))
    js = [f"// {HEADER}", "// Path data on the Material Symbols 960 grid (viewBox \"0 -960 960 960\"), keyed by action.",
          f"globalThis.{PRODUCT}Icons = {{"]
    for a in ICONS:
        js.append(f'  "{a}": "{icon_source(a, "material")[1]}",')
    js += ["};", ""]
    out["web/icons.js"] = "\n".join(js)
    for a in ICONS:
        _, d = icon_source(a, "material")
        out[f"web/icons/{a}.svg"] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" width="24" height="24" '
                                     f'fill="currentColor" aria-hidden="true"><path d="{d}"/></svg>\n')
    return out


# ---------------------------------------------------------------- icon map (docs)

def icon_map() -> str:
    L = [f"<!-- {HEADER} -->", "# Icon map", "",
         "One icon per action on every platform. The label is always shown (or is the accessible name in the transport row).",
         "Custom glyphs live in `design/brand/icons/custom/`.", "",
         "| Action | English | Norsk (bokmål) | Apple (SF Symbols) | Android and Studio (Material Symbols Rounded) | Windows (Segoe Fluent Icons) |",
         "|---|---|---|---|---|---|"]
    for a, v in ICONS.items():
        m = v["material"]
        m = f"`{m}`" if isinstance(m, str) else f"custom `{m['custom']}`"
        w = v["windows"]
        w = f"`{w['name']}` U+{w['glyph']}" if "glyph" in w else f"custom `{w['custom']}` (PathIcon)"
        L.append(f"| {a} | {v['en']} | {v['nb']} | `{v['apple']}` | {m} | {w} |")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- main

def outputs() -> dict[Path, str | bytes]:
    out: dict[Path, str | bytes] = {}
    platforms = {"apple": apple_outputs, "android": android_outputs, "windows": windows_outputs, "web": web_outputs}
    for name, fn in platforms.items():
        if ONLY in (None, name):
            for path, content in fn().items():
                out[DIST / path] = content
    if ONLY is None:
        out[DIST / "icon-map.md"] = icon_map()
        if "a11yCompat" in EXT:  # the palette Play and Studio are checked against; one brand has it
            out[ROOT / EXT["a11yCompat"]["file"]] = a11y_json()
    return out


def as_bytes(c: str | bytes) -> bytes:
    return c.encode() if isinstance(c, str) else c


def generated_dirs() -> tuple[str, ...]:
    """The folders that hold generated files only, so a file this run does not write there is a leftover."""
    return (f"apple/{PRODUCT}Design.xcassets", "android/kotlin", "android/res/drawable", "web/icons")


def leftovers(want: dict[Path, str | bytes]) -> list[Path]:
    """Files in the generated folders (of the platforms this run writes) that it no longer writes."""
    found = []
    for d in generated_dirs():
        base = DIST / d
        if ONLY in (None, d.split("/")[0]) and base.exists():
            found += [f for f in base.rglob("*") if f.is_file() and f not in want and not f.name.startswith("ic_launcher")]
    return found


def stale() -> list[str]:
    want = outputs()
    bad = [rel(p) for p, c in want.items() if not p.exists() or p.read_bytes() != as_bytes(c)]
    bad += [rel(f) + " (not generated any more)" for f in leftovers(want)]
    return sorted(bad)


def command() -> str:
    """The command that writes this run's outputs, as it is typed from the repository root."""
    brand = brand_of(TOKENS_FILE)
    args = f" --brand {brand['name']}" if brand and DIST == (ROOT / brand["out"]).resolve() else f" --tokens {rel(TOKENS_FILE)} --out {rel(DIST)}"
    return f"uv run design/tokens/build.py{args}" + (f" --only {ONLY}" if ONLY else "")


def write() -> None:
    want = outputs()
    for f in leftovers(want):
        f.unlink()
    for p, c in want.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(as_bytes(c))
    print(f"wrote {len(want)} files to {rel(DIST)}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate platform code from design tokens.")
    parser.add_argument("--check", action="store_true", help="exit 1 if any output is missing or out of date")
    parser.add_argument("--brand", choices=[b["name"] for b in BRANDS], help="one brand of brands.json (default: every brand)")
    parser.add_argument("--tokens", type=Path, help="a token file that is not in brands.json; needs --out")
    parser.add_argument("--out", type=Path, help="the output folder of --tokens")
    parser.add_argument("--only", choices=PLATFORMS, help="write this platform only")
    args = parser.parse_args(argv)
    if args.tokens or args.out:
        if args.brand or not args.tokens:
            parser.error("--tokens and --out go together, without --brand")
        brand = brand_of(args.tokens)
        if not args.out and not brand:
            parser.error("--tokens needs --out")
        runs = [(args.tokens, args.out or ROOT / brand["out"])]
    else:
        runs = [(ROOT / b["tokens"], ROOT / b["out"]) for b in BRANDS if args.brand in (None, b["name"])]
    failed = False
    for tokens, out in runs:
        configure(tokens, out, args.only)
        if not args.check:
            write()
            continue
        bad = stale()
        if bad:
            failed = True
            print(f"Design outputs are out of date. Run `{command()}`:")
            print("\n".join("  " + b for b in bad))
        else:
            print(f"design outputs are in sync: {rel(DIST)}")
    return 1 if failed else 0


configure()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
