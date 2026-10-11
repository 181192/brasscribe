"""The generated platform files must match the tokens. Run: uv run --with pytest pytest design/tokens"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("design_build", HERE / "build.py")
build = importlib.util.module_from_spec(spec)
sys.modules["design_build"] = build
spec.loader.exec_module(build)


def test_outputs_in_sync():
    stale = build.stale()
    assert not stale, "run `uv run design/tokens/build.py`; stale: " + ", ".join(stale)


def test_every_mode_defines_every_role():
    modes = build.TOKENS["color"]
    light = set(build.roles())
    for mode in build.MODES:
        assert set(k for k in modes[mode] if not k.startswith("$")) == light, mode


def test_a11y_palette_is_unchanged_where_agreed():
    # The score hues were agreed with accessibility review; only the neutrals may move.
    agreed = {"uncertain": "#0063A6", "very-uncertain": "#B04A00", "cursor": "#6B3FA0",
              "loop-tint": "#FFF3D6", "loop-edge": "#8A5A00", "error": "#B3261E"}
    for role, hexv in agreed.items():
        assert build.hexval("light", role) == hexv, role


def test_every_icon_has_all_platforms_and_sources():
    for action, v in build.ICONS.items():
        for key in ("en", "nb", "apple", "material", "windows"):
            assert v.get(key), (action, key)
        for platform in ("material", "windows"):
            kind, value = build.icon_source(action, platform)
            assert value, (action, platform)


def test_compat_file_keeps_its_shape():
    data = json.loads((build.ROOT / "docs" / "accessibility" / "design-tokens.json").read_text())
    assert set(data) >= {"themes", "pairs", "distinguish", "legacy"}
    assert set(data["themes"]) == {"light", "dark", "high-contrast"}


def test_focus_never_looks_like_uncertainty():
    # The focus ring sits on notation; it must not share a hue family with the uncertainty colours.
    import sys
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    for mode in ("light", "dark", "high-contrast-light"):
        for role in ("uncertain", "very-uncertain"):
            de = contrast.delta_e(build.hexval(mode, "focus"), build.hexval(mode, role), None)
            assert de >= 20, (mode, role, de)


def test_light_high_contrast_is_seven_to_one():
    # Every checked pair reaches WCAG AAA (7:1) on the light high-contrast palette.
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    for fg, bg, _, _ in build.EXT["contrast"]["pairs"]:
        r = contrast.contrast(build.hexval("high-contrast-light", fg), build.hexval("high-contrast-light", bg))
        assert r >= 7, (fg, bg, round(r, 2))


def test_web_high_contrast_follows_the_resolved_theme():
    css = (build.DIST / "web" / "brasscribe.css").read_text()
    more = "@media (prefers-contrast: more) and (forced-colors: none)"
    assert f'{more} {{\n  :root:not([data-theme="dark"]) {{\n    color-scheme: light;\n    --scribe-bg: #FFFFFF;' in css
    assert f'{more} and (prefers-color-scheme: dark) {{\n  :root:not([data-theme="light"]) {{\n    color-scheme: dark;\n    --scribe-bg: #000000;' in css
    assert f'{more} {{\n  :root[data-theme="dark"] {{\n    color-scheme: dark;\n    --scribe-bg: #000000;' in css


def test_pink_keeps_the_notation_and_its_meaning():
    # Pink recolours the chrome only: the notation stays black on light (paper tones on dark) and the
    # score hues keep their meaning.
    for pink, base in (("pink", "light"), ("pink-dark", "dark")):
        for role in ("ink", "staff", "uncertain", "very-uncertain", "loop-edge", "cursor", "success", "warning", "brass"):
            if (pink, role) == ("pink", "very-uncertain"):
                continue
            assert build.hexval(pink, role) == build.hexval(base, role), (pink, role)


def test_pink_very_unsure_is_the_same_orange_a_shade_darker():
    # Pink's tonal fills are darker than Light's, so the very-unsure "?" on one needs a darker orange to
    # stay readable as text (4.5:1). It keeps its hue: next to Light's it is the same colour, only darker.
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import colorsys
    import contrast

    def hls(mode):
        h = build.hexval(mode, "very-uncertain")
        return colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)))

    (hue, light, _), (pink_hue, pink_light, _) = hls("light"), hls("pink")
    assert abs(hue - pink_hue) * 360 < 2 and pink_light < light
    assert contrast.delta_e(build.hexval("light", "very-uncertain"), build.hexval("pink", "very-uncertain"), None) < 5
    for ground in ("secondary", "brass-tint", "surface", "bg"):
        r = contrast.contrast(build.hexval("pink", "very-uncertain"), build.hexval("pink", ground))
        assert r >= 4.5, (ground, round(r, 2))


def test_pink_status_and_primary_stay_apart():
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    for mode in ("pink", "pink-dark"):
        for a, b in (("error", "primary"), ("success", "error"), ("warning", "error"), ("success", "warning"),
                     ("focus", "uncertain"), ("focus", "very-uncertain")):
            de = contrast.delta_e(build.hexval(mode, a), build.hexval(mode, b), None)
            assert de >= 20, (mode, a, b, round(de, 1))


def test_every_platform_gets_the_pink_palette():
    css = (build.DIST / "web" / "brasscribe.css").read_text()
    assert ':root[data-palette="pink"] {\n    color-scheme: light;\n    --scribe-bg: #FFF6F9;' in css
    assert "(not (prefers-contrast: more))" in css
    kt = (build.DIST / "android" / "kotlin" / "no" / "brasscribe" / "design" / "BrasscribeTheme.kt").read_text()
    assert "val BrasscribePinkColors" in kt and "pink && dark -> BrasscribePinkDarkColors" in kt
    assert kt.index("highContrast -> ") < kt.index("pink && dark -> ")
    cs = json.loads((build.DIST / "apple" / "BrasscribeDesign.xcassets" / "BrasscribePink" / "bg.colorset" / "Contents.json").read_text())
    assert [c["color"]["components"]["red"] for c in cs["colors"]][:1] == [build.rgb_components("#FFF6F9")[0]]
    assert len(cs["colors"]) == 4  # light, dark and both high-contrast appearances
    assert "Pink" not in (build.DIST / "windows" / "BrasscribeTheme.xaml").read_text()
    xaml = (build.DIST / "windows" / "BrasscribePinkTheme.xaml").read_text()
    light, dark = xaml.index('x:Key="Light"'), xaml.index('x:Key="Dark"')
    assert xaml.index('<Color x:Key="ScribeBgColor">#FFFFF6F9</Color>') in range(light, dark)
    assert xaml.index('<Color x:Key="ScribePrimaryColor">#FFFF9ECF</Color>') > dark
    assert 'x:Key="HighContrast"' in xaml


# ---------------------------------------------------------------- every brand, every platform

FRETSCRIBE = build.ROOT / "design" / "fretscribe"
KOTLIN = Path("android") / "kotlin" / "no" / "brasscribe" / "design"
# Words that belong to one brand's idea of its product; no neutral name may carry them.
BRAND_WORDS = ("brass", "staff", "score", "string", "tab", "fret", "pink", "adlib", "model")


def product_build(tokens: Path, out: Path, only: str | None = None):
    """A second copy of the generator set up for another product, so `build` stays Brasscribe's."""
    s = importlib.util.spec_from_file_location("design_build_product", HERE / "build.py")
    module = importlib.util.module_from_spec(s)
    s.loader.exec_module(module)
    module.configure(tokens, out, only)
    return module


def fretscribe():
    return product_build(FRETSCRIBE / "tokens" / "tokens.json", FRETSCRIBE / "dist")


def brands():
    """Every brand of brands.json, each with its own copy of the generator."""
    return {b["name"]: product_build(build.ROOT / b["tokens"], build.ROOT / b["out"]) for b in build.BRANDS}


def declarations(kotlin: str) -> list[str]:
    """Every declared name of a generated Kotlin file, in order: types, functions, values and fields."""
    import re
    return re.findall(r"^\s*(?:@\w+\s+)*((?:data class|enum class|object|fun|const val|val|typealias)\s+[\w.]+|[A-Z_]+(?=\())", kotlin, re.M)


def test_every_brand_is_generated_for_every_platform_and_in_sync():
    assert set(brands()) >= {"brasscribe", "fretscribe"}
    for name, b in brands().items():
        stale = b.stale()
        assert not stale, f"run `{b.command()}`; stale: " + ", ".join(stale)
        want = b.outputs()
        for platform in build.PLATFORMS:
            assert any(p.is_relative_to(b.DIST / platform) for p in want), (name, platform)
        assert b.DIST / "icon-map.md" in want, name
    assert fretscribe().main(["--check"]) == 0  # a copy: main sets the copy up for each brand in turn


def test_every_brand_defines_every_role_in_every_mode():
    for name, b in brands().items():
        light = set(b.roles())
        assert set(b.MODES) >= set(build.NEUTRAL["modes"]), name
        for mode in b.MODES:
            assert set(k for k in b.TOKENS["color"][mode] if not k.startswith("$")) == light, (name, mode)


def test_every_brand_passes_its_contrast_pairs_in_every_mode():
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    for name, b in brands().items():
        assert b.EXT["contrast"]["pairs"], name
        for mode in b.MODES:
            for fg, bg, minimum, _ in b.EXT["contrast"]["pairs"]:
                r = contrast.contrast(b.hexval(mode, fg), b.hexval(mode, bg))
                assert r + 1e-9 >= minimum, (name, mode, fg, bg, round(r, 2))
        # Light high contrast reaches WCAG AAA, and the focus ring never looks like doubt.
        for fg, bg, _, _ in b.EXT["contrast"]["pairs"]:
            assert contrast.contrast(b.hexval("high-contrast-light", fg), b.hexval("high-contrast-light", bg)) >= 7, (name, fg, bg)
        for mode in ("light", "dark", "high-contrast-light"):
            assert contrast.delta_e(b.hexval(mode, "focus"), b.hexval(mode, b.neutral_roles()["uncertain"]), None) >= 20, (name, mode)


def test_light_very_uncertain_keeps_its_margin():
    # The tightest pair of the palette: Light's very-uncertain "?" on a tonal fill.
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    assert round(contrast.contrast(build.hexval("light", "very-uncertain"), build.hexval("light", "secondary")), 2) == 4.53


# ---------------------------------------------------------------- the neutral names

def swift_types(text: str) -> dict[str, list[str]]:
    """The members of every type a generated Swift file declares, by the type's full name (Color.Scribe,
    ScribeDesign.Space): the nesting is read from the braces."""
    import re
    found: dict[str, list[str]] = {}
    stack: list[tuple[str, int]] = []
    depth = 0
    for line in text.splitlines():
        opened = re.match(r"\s*(?:public |private |final )*(?:enum|extension|class) ([\w.]+)[^{]*\{\s*$", line)
        if opened:
            stack.append((opened.group(1), depth))
            found.setdefault(".".join(n for n, _ in stack), [])
        elif stack:
            member = re.match(r"\s*(?:public |private )?(?:static let|static var|static func|case|var) (\w+)", line)
            if member and depth == stack[-1][1] + 1:
                found[".".join(n for n, _ in stack)].append(member.group(1))
        depth += line.count("{") - line.count("}")
        while stack and depth <= stack[-1][1]:
            stack.pop()
    return found


def swift_neutral(b) -> dict[str, list[str]]:
    """The neutral types of a brand's Swift file and their members."""
    types = swift_types((b.DIST / "apple" / f"{b.PRODUCT}Design.swift").read_text())
    return {k: sorted(v) for k, v in types.items() if "Scribe" in k}


def neutral_names(b) -> dict[str, list[str]]:
    """The neutral names each platform's files declare for a brand, in order."""
    import re
    product = b.PRODUCT
    xaml = (b.DIST / "windows" / f"{product}Theme.xaml").read_text()
    css = (b.DIST / "web" / f"{product.lower()}.css").read_text()
    return {
        "apple": sorted(f"{t}.{m}" for t, ms in swift_neutral(b).items() for m in ms),
        "android": declarations((b.DIST / KOTLIN / "ScribeTheme.kt").read_text()),
        "windows": re.findall(r'x:Key="(Scribe\w+)"', xaml),
        "web": sorted(set(re.findall(r"^\s+(--scribe-[\w-]+):", css, re.M))),
    }


def test_every_brand_declares_the_same_neutral_names():
    # Shared code compiles against any brand: the neutral names are the same, on every platform.
    found = {name: neutral_names(b) for name, b in brands().items()}
    ours = found["brasscribe"]
    for platform, names in ours.items():
        assert len(names) > 15, platform
        for name, theirs in found.items():
            assert sorted(theirs[platform]) == sorted(names), (name, platform)  # a brand orders its roles its own way


def test_neutral_names_cover_the_neutral_roles_and_nothing_of_one_brand():
    import re
    for name, b in brands().items():
        found = neutral_names(b)
        for role in build.NEUTRAL["roles"]:
            assert f"Color.Scribe.{build.camel(role)}" in found["apple"], (name, role)
            assert f"Scribe{build.pascal(role)}Brush" in found["windows"], (name, role)
            assert f"--scribe-{role}" in found["web"], (name, role)
        for platform, names in found.items():
            for n in names:
                words = [w.lower() for w in re.findall(r"[A-Za-z][a-z]*", n.replace("Scribe", "").replace("scribe", ""))]
                assert not set(words) & set(BRAND_WORDS), (name, platform, n)
    for role in build.NEUTRAL["roles"]:
        assert not set(role.split("-")) & set(BRAND_WORDS), role


def test_the_action_icons_have_no_neutral_name():
    # The actions of icons.json are one product's so far (the talking score, the music stand), so the icons
    # stay under each brand's own name.
    for name, b in brands().items():
        for path in (b.DIST / "apple" / f"{b.PRODUCT}Design.swift", b.DIST / KOTLIN / "ScribeTheme.kt",
                     b.DIST / "windows" / f"{b.PRODUCT}Theme.xaml", b.DIST / "web" / "icons.js"):
            assert "ScribeIcon" not in path.read_text(), (name, path.name)


def test_no_xaml_dictionary_has_a_key_twice():
    # WinUI refuses a dictionary with a key twice, and nothing compiles a brand's theme before an app uses it.
    import xml.etree.ElementTree as ET
    x = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
    rd = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}ResourceDictionary"
    for name, b in brands().items():
        files = sorted((b.DIST / "windows").glob("*.xaml"))
        assert files, name
        for file in files:
            for dictionary in ET.parse(file).getroot().iter(rd):
                keys = [e.get(x) for e in dictionary if e.get(x)]
                assert len(keys) == len(set(keys)), (file.name, dictionary.get(x), [k for k in keys if keys.count(k) > 1][:3])


def test_neutral_colours_have_the_brands_values_in_every_theme():
    import re
    import xml.etree.ElementTree as ET
    x = "{http://schemas.microsoft.com/winfx/2006/xaml}"
    for name, b in brands().items():
        root = ET.parse(b.DIST / "windows" / f"{b.PRODUCT}Theme.xaml").getroot()  # well-formed
        themes = {d.get(f"{x}Key"): {e.get(f"{x}Key"): (e.text or e.get("ResourceKey") or e.get("Color")) for e in d}
                  for d in root.iter("{http://schemas.microsoft.com/winfx/2006/xaml/presentation}ResourceDictionary") if d.get(f"{x}Key")}
        assert set(themes) == {"Light", "Dark", "HighContrast"}, name
        # Windows: a neutral role has its Scribe key with the brand's value (in a contrast theme the neutral
        # role's system colour) and no key under the brand's prefix; the brand's own roles have only that.
        modes = {"Light": "light", "Dark": "dark"}
        for theme, keys in themes.items():
            for role, src in b.neutral_roles().items():
                neutral = f"Scribe{b.pascal(role)}"
                assert f"{b.KEY}{b.pascal(src)}Color" not in keys and f"{b.KEY}{b.pascal(src)}Brush" not in keys, (name, theme, src)
                if theme == "HighContrast":
                    assert keys[f"{neutral}Color"] == build.NEUTRAL["roles"][role]["windows"], (name, role)
                else:
                    assert keys[f"{neutral}Color"] == f"#{round(b.alpha(modes[theme], src) * 255):02X}{b.hexval(modes[theme], src)[1:]}", (name, theme, role)
                assert f"{neutral}Brush" in keys, (name, theme, role)
            for role in b.own_roles():
                assert f"{b.KEY}{b.pascal(role)}Brush" in keys and f"Scribe{b.pascal(role)}Brush" not in keys, (name, theme, role)
        rest = {e.get(f"{x}Key") for e in root if e.get(f"{x}Key")}
        assert {"ScribeSpace4", "ScribePadding4", "ScribeRadiusMd", "ScribeTouchMin", "ScribeDurationFast", "ScribeDisplayFontFamily",
                "ScribeBodyTextBlockStyle"} <= rest, name
        view = b.pascal(b.EXT["notation"])
        assert {f"{b.KEY}{view}CursorWidth", f"{b.KEY}IconPlay"} <= rest, name
        assert not {k for k in rest if k.startswith(b.KEY) and not k.startswith((f"{b.KEY}{view}", f"{b.KEY}Icon", f"{b.KEY}TabFontFamily"))}, name
        css = (b.DIST / "web" / f"{b.PRODUCT.lower()}.css").read_text()
        # The web: a neutral role is declared once, under its neutral name, with the brand's value in every
        # mode; the brand's prefix is left for what is the brand's own.
        root = css.split(":root {", 1)[1].split("}", 1)[0]
        for role, src in b.neutral_roles().items():
            assert f"  --scribe-{role}: {b.css_color('light', src)};" in root, (name, role)
            assert f"--{b.CSS}-{src}:" not in css, (name, src)
        own = set(re.findall(rf"--{b.CSS}-([a-z0-9-]+):", css))
        assert own and not {o for o in own if o in build.NEUTRAL["roles"] or o.startswith(("space-", "radius-", "duration-", "font-text"))}, name
        assert set(re.findall(r"var\((--[\w-]+)\)", css)) <= set(re.findall(r"^\s+(--[\w-]+):", css, re.M)), name
        blocks = [set(re.findall(r"(--[\w-]+):", blk)) for blk in css.split("{")[1:] if "--scribe-bg:" in blk]
        assert len(blocks) >= 8 and all({f"--scribe-{r}" for r in build.NEUTRAL["roles"]} <= blk for blk in blocks), name


def test_system_colours_go_by_the_name_a_role_is_read_under():
    # A token that two neutral roles read (the accent and brand text) has each role's system colour under
    # the neutral names, and under the brand's own name the one the brand's tokens say.
    for name, b in brands().items():
        token = b.neutral_roles()["accent"]
        assert token == b.neutral_roles()["brand-text"], name
        xaml = (b.DIST / "windows" / f"{b.PRODUCT}Theme.xaml").read_text()
        assert '<StaticResource x:Key="ScribeAccentColor" ResourceKey="SystemColorHotlightColor"/>' in xaml, name
        assert '<StaticResource x:Key="ScribeBrandTextColor" ResourceKey="SystemColorWindowTextColor"/>' in xaml, name
        forced = (b.DIST / "web" / f"{b.PRODUCT.lower()}.css").read_text().split("@media (forced-colors: active)")[1]
        assert "--scribe-accent: LinkText;" in forced and "--scribe-brand-text: CanvasText;" in forced, name


def test_every_variable_the_web_clients_read_is_declared():
    # A style that reads a variable the style sheet does not declare fails silently, so a name that no
    # longer exists (a brand-named copy of a neutral role) is caught here.
    import re
    declared = set(re.findall(r"(--[\w-]+):", (build.DIST / "web" / "brasscribe.css").read_text()))
    read, checked = {}, 0
    for folder in ("studio/src", "studio/browser", "site", "design/mockups"):
        for path in (build.ROOT / folder).rglob("*"):
            if path.suffix in (".css", ".ts", ".js", ".mjs", ".html") and "_site" not in path.parts and "node_modules" not in path.parts:
                checked += 1
                for name in re.findall(r"--(?:bc|scribe)-[a-z0-9]+(?:-[a-z0-9]+)*", path.read_text()):
                    if name not in declared:
                        read.setdefault(name, path.relative_to(build.ROOT).as_posix())
    assert checked > 50 and not read, read
    # Studio's canvases read variables by name from code: token("scribe-text"), tokenColour("bc-model-2") and
    # the layers' colour: "…". Each name is a declared variable's, never a short name of Studio's own.
    named = 0
    for path in (build.ROOT / "studio" / "src").rglob("*.ts"):
        text = path.read_text()
        calls = [m.group(1) for m in re.finditer(r"\btoken(?:Colour)?\(((?:[^()]|\([^()]*\))*)\)", text)]
        names = [n for call in calls for n in re.findall(r'"([^"]*)"', re.sub(r'[!=]==? "[^"]*"', "", call))]  # not what is compared
        names += re.findall(r'\b(?:colour|token): "([^"]*)"', text)
        for name in names:
            named += 1
            assert f"--{name}" in declared, (path.name, name)
    assert named > 40, named
    assert not (build.ROOT / "studio" / "src" / "tokens.css").exists()


def test_pink_follows_into_the_neutral_names_on_windows():
    # The Pink dictionary is merged after the theme, so it carries the neutral keys with Pink's values.
    xaml = (build.DIST / "windows" / "BrasscribePinkTheme.xaml").read_text()
    assert '<Color x:Key="ScribeBgColor">#FFFFF6F9</Color>' in xaml
    assert xaml.count('x:Key="ScribeBgBrush"') == 3


def test_neutral_types_have_the_same_members_in_every_brand():
    # A neutral type that only pointed at a brand's would show that brand's own members too (a tab font, a
    # score metric). So the members are compared, not only the names of the types.
    import re

    def members(text: str, opening: str) -> list[str]:
        body = text.split(opening, 1)[1]
        return sorted(re.findall(r"(?:const val|val) (\w+)", body[:body.index("\n}")]))

    found = {}
    for name, b in brands().items():
        kotlin = (b.DIST / KOTLIN / "BrasscribeTheme.kt").read_text()
        found[name] = {**swift_neutral(b), **{f"Scribe{t}": members(kotlin, "object Brasscribe" + t + " {") for t in ("Space", "Size", "Motion")}}
        assert set(found[name]) >= {"ScribeDesign", "ScribeDesign.Space", "ScribeDesign.Radius", "ScribeDesign.Size", "ScribeDesign.Motion",
                                    "Color.Scribe", "Font.Scribe"}, name
        assert found[name]["Color.Scribe"] == sorted(build.camel(r) for r in build.NEUTRAL["roles"]), name
        assert "tab" not in found[name]["Font.Scribe"] and "title1" in found[name]["Font.Scribe"], name
        assert "s4" in found[name]["ScribeDesign.Space"] and "animation" in found[name]["ScribeDesign.Motion"], name
    for name, theirs in found.items():
        assert theirs == found["brasscribe"], name


def test_swift_has_one_name_for_each_role():
    # Apple: a neutral role or scale is on the Scribe types only, and a brand's type holds only what is the
    # brand's own, so code cannot read a neutral role under a brand's name.
    for name, b in brands().items():
        types = swift_types((b.DIST / "apple" / f"{b.PRODUCT}Design.swift").read_text())
        own = sorted(b.camel(r) for r in b.roles() if r not in b.neutral_roles().values())
        assert sorted(types[f"Color.{b.PRODUCT}"]) == own and own, name
        assert not set(types[f"Color.{b.PRODUCT}"]) & set(types["Color.Scribe"]), name
        assert not set(types[f"Font.{b.PRODUCT}"]) & set(types["Font.Scribe"]), name
        view = b.pascal(b.EXT["notation"])
        assert [k for k in types if k.startswith(f"{b.PRODUCT}Design")] == [f"{b.PRODUCT}Design", f"{b.PRODUCT}Design.{view}"], name
        assert types[f"{b.PRODUCT}Design"] == [] and "cursorWidth" in types[f"{b.PRODUCT}Design.{view}"], name
    fs = swift_types((fretscribe().DIST / "apple" / "FretscribeDesign.swift").read_text())
    assert fs["Font.Fretscribe"] == ["tab"] and "uncertainTint" in fs["Color.Fretscribe"]
    assert swift_types((build.DIST / "apple" / "BrasscribeDesign.swift").read_text())["Font.Brasscribe"] == []


def test_accent_is_for_what_you_act_on_and_brand_is_identity():
    # The accent carries links and progress, so it is readable as text on every plain ground, in every mode
    # of every brand, and each brand lists those pairs. The brand colour is not checked as text.
    sys.path.insert(0, str(build.ROOT / "qa" / "tools"))
    import contrast
    for name, b in brands().items():
        accent = b.neutral_roles()["accent"]
        assert accent != b.neutral_roles()["brand"], name
        for ground in ("bg", "surface", "surface-raised"):
            assert [p for p in b.EXT["contrast"]["pairs"] if p[:2] == [accent, ground] and p[2] >= 4.5], (name, ground)
            for mode in b.MODES:
                assert contrast.contrast(b.hexval(mode, accent), b.hexval(mode, ground)) >= 4.5, (name, mode, ground)


# A brand that lacks something is told what, in words, when the generator is set up.

def broken(tmp_path, change, source=None) -> Path:
    """A copy of a brand's tokens (Fretscribe's) with one thing changed; its font paths still lead to the fonts."""
    source = source or FRETSCRIBE / "tokens" / "tokens.json"
    raw = json.loads(source.read_text())
    ext = next(v for v in raw["$extensions"].values() if isinstance(v, dict) and "modes" in v)
    for font in [v for k, v in ext["fonts"].items() if not k.startswith("$")]:
        font["licence"] = str((source.parent / font["licence"]).resolve())
        for face in font["faces"]:
            face["file"] = str((source.parent / face["file"]).resolve())
    for key in ("file", "licence"):
        if "display-font" in ext.get("android", {}):
            ext["android"]["display-font"][key] = str((source.parent / ext["android"]["display-font"][key]).resolve())
    ext["prefix"] = "tmp"  # a copy has the brand's prefix, which no second brand may have
    change(raw, ext)
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps(raw))
    return tokens


def refused(tmp_path, change, message, source=None):
    import pytest
    with pytest.raises(SystemExit, match=message):
        product_build(broken(tmp_path, change, source), tmp_path / "dist")


def test_an_unchanged_copy_of_a_brand_is_accepted(tmp_path):
    fs = product_build(broken(tmp_path, lambda raw, ext: None), tmp_path / "dist")
    assert len(fs.outputs()) > 100


def test_a_neutral_role_the_brand_neither_has_nor_maps_is_an_error(tmp_path):
    refused(tmp_path, lambda raw, ext: ext["neutral"]["roles"].pop("line"), "no token for the neutral role 'line'")


def test_a_brands_own_role_needs_its_system_colour(tmp_path):
    refused(tmp_path, lambda raw, ext: ext["system-colours"].pop("uncertain-tint"), r"no system colour \(windows\) for 'uncertain-tint'")


def test_the_neutral_prefix_is_no_brands(tmp_path):
    refused(tmp_path, lambda raw, ext: ext.update(prefix="scribe"), "'scribe' is the prefix of the neutral names")
    refused(tmp_path, lambda raw, ext: ext.update(prefix="Fs"), "must be lower-case letters and digits")
    refused(tmp_path, lambda raw, ext: raw["$extensions"].update({"no.scribe": raw["$extensions"].pop("no.fretscribe")}) or ext.pop("prefix"),
            "'scribe' is the prefix of the neutral names")


def test_two_brands_cannot_have_one_prefix(tmp_path):
    # Also for a token file that is not in brands.json: a copy of a brand's file has that brand's prefix.
    refused(tmp_path, lambda raw, ext: ext.update(prefix="bc"), "the prefix 'bc' is brasscribe's too")
    refused(tmp_path, lambda raw, ext: ext.update(prefix="fs"), "the prefix 'fs' is fretscribe's too")


def test_brands_json_is_checked():
    import pytest
    ok = {"name": "a", "tokens": "design/a/tokens.json", "out": "design/a/dist"}
    build.check_brands([ok, {"name": "b", "tokens": "design/b/tokens.json", "out": "design/b/dist"}])
    for key in ("name", "tokens", "out"):
        with pytest.raises(SystemExit, match=f"has no '{key}'"):
            build.check_brands([{k: v for k, v in ok.items() if k != key}])
    with pytest.raises(SystemExit, match="a and A have the same name"):
        build.check_brands([ok, {**ok, "name": "A", "tokens": "x.json", "out": "x"}])
    with pytest.raises(SystemExit, match="a and b have the same output folder"):
        build.check_brands([ok, {**ok, "name": "b", "tokens": "x.json"}])
    with pytest.raises(SystemExit, match="a and b have the same token file"):
        build.check_brands([ok, {**ok, "name": "b", "out": "x"}])


def test_a_brand_with_something_missing_is_told_what(tmp_path):
    refused(tmp_path, lambda raw, ext: ext.pop("notation"), r"no \$extensions.\*.notation")
    refused(tmp_path, lambda raw, ext: ext.update(notation="stave"), "names the group 'stave', which the file does not have")
    refused(tmp_path, lambda raw, ext: ext["fonts"].pop("display"), r"no \$extensions.\*.fonts.display")
    refused(tmp_path, lambda raw, ext: ext.pop("fonts"), r"no \$extensions.\*.fonts.display")
    refused(tmp_path, lambda raw, ext: ext["fonts"]["tab"].pop("licence"), r"fonts.tab has no 'licence'")
    refused(tmp_path, lambda raw, ext: ext["fonts"]["tab"]["faces"][0].update(file="nowhere.ttf"), "names nowhere.ttf, which is not there")
    refused(tmp_path, lambda raw, ext: raw["color"]["dark"].pop("focus"), r"color.dark lacks focus")
    refused(tmp_path, lambda raw, ext: raw["color"]["dark"].update(glow=raw["color"]["dark"]["focus"]), r"color.dark has glow that color.light lacks")
    refused(tmp_path, lambda raw, ext: ext["modes"].remove("high-contrast-light"), "the mode 'high-contrast-light' is not listed")
    refused(tmp_path, lambda raw, ext: ext["modes"].append("sepia"), "the mode 'sepia' is listed .* and has no colours")
    for name in ("typography", "space", "size", "radius", "elevation", "motion", "font", "color"):
        refused(tmp_path, lambda raw, ext, name=name: raw.pop(name), f"tokens.json: no '{name}' group")
    refused(tmp_path, lambda raw, ext: ext.pop("modes"), r"tokens.json: expected one \$extensions entry with modes and contrast")
    refused(tmp_path, lambda raw, ext: ext.pop("contrast"), r"tokens.json: expected one \$extensions entry with modes and contrast")


# ---------------------------------------------------------------- Fretscribe

def test_fretscribe_has_its_own_names_and_none_of_brasscribes():
    # Apple, Windows and the web: Fretscribe's files say Fretscribe, Fs and --fs-, and its own roles are there.
    fs = fretscribe()
    swift = (fs.DIST / "apple" / "FretscribeDesign.swift").read_text()
    xaml = (fs.DIST / "windows" / "FretscribeTheme.xaml").read_text()
    css = (fs.DIST / "web" / "fretscribe.css").read_text()
    js = (fs.DIST / "web" / "icons.js").read_text()
    for text in (swift, xaml, css, js, (fs.DIST / "web" / "fonts.css").read_text()):
        body = text.split("\n", 1)[1]  # the header names the generator's path
        assert "rasscribe" not in body and "--bc-" not in body and 'x:Key="Bc' not in body and "Pink" not in body
        assert "Instrument" not in body
    assert "public static var uncertainTint: Color" in swift and 'public static var line: Color { catalogColor("string") }' in swift
    assert "public enum Tab {" in swift and "enum Fretscribe {" in swift
    assert 'x:Key="FsUncertainTintBrush"' in xaml and 'x:Key="ScribeLineBrush"' in xaml and 'x:Key="FsStringBrush"' not in xaml and 'x:Key="FsTabCursorWidth"' in xaml
    assert "--fs-uncertain-tint: #FCF0DB;" in css and "--scribe-line: #737983;" in css and "--fs-tab-cursor-width:" in css
    assert "globalThis.FretscribeIcons = {" in js
    assert not (fs.DIST / "windows" / "FretscribePinkTheme.xaml").exists()
    sets = fs.DIST / "apple" / "FretscribeDesign.xcassets"
    assert sorted(p.name for p in sets.iterdir()) == ["Contents.json", "Fretscribe"]
    assert sorted(p.name for p in (sets / "Fretscribe").iterdir() if p.suffix == ".colorset") == \
        sorted(f"{fs.camel(r)}.colorset" for r in fs.roles())


def test_fretscribe_fonts_and_licences_are_staged_on_every_platform():
    fs = fretscribe()
    source = FRETSCRIBE / "brand" / "fonts"
    names = ["AtkinsonHyperlegibleNext-wght.ttf", "FretscribeTab-Regular.ttf",
             "OFL-AtkinsonHyperlegibleNext.txt", "OFL-FretscribeTab.txt"]
    for folder in ("apple/Fonts", "windows/Assets/Fonts", "web/fonts"):
        assert sorted(p.name for p in (fs.DIST / folder).iterdir()) == names, folder
        for n in names:
            assert (fs.DIST / folder / n).read_bytes() == (source / n).read_bytes(), (folder, n)
    swift = (fs.DIST / "apple" / "FretscribeDesign.swift").read_text()
    # The titles: the brand's own face, at the weight its display token names; the fret numbers: the tab face.
    assert '.custom("AtkinsonHyperlegibleNext-Regular", size: 40, relativeTo: .largeTitle).weight(.semibold)' in swift
    assert 'public static func tab(size: CGFloat) -> Font { .custom("FretscribeTab-Regular", size: size) }' in swift
    xaml = (fs.DIST / "windows" / "FretscribeTheme.xaml").read_text()
    assert "ms-appx:///Assets/Fonts/AtkinsonHyperlegibleNext-wght.ttf#Atkinson Hyperlegible Next" in xaml
    assert "ms-appx:///Assets/Fonts/FretscribeTab-Regular.ttf#Fretscribe Tab" in xaml
    fonts = (fs.DIST / "web" / "fonts.css").read_text()
    assert fonts.count("@font-face") == 2 and "font-weight: 200 800;" in fonts and "OFL-FretscribeTab.txt" in fonts
    assert '--fs-font-tab: "Fretscribe Tab", ui-monospace, monospace;' in (fs.DIST / "web" / "fretscribe.css").read_text()


def test_brasscribe_fonts_are_staged_as_before():
    assert sorted(p.name for p in (build.DIST / "web" / "fonts").iterdir()) == ["InstrumentSerif-Italic.ttf", "InstrumentSerif-Regular.ttf", "OFL.txt"]
    for folder in ("apple/Fonts", "windows/Assets/Fonts"):
        assert sorted(p.name for p in (build.DIST / folder).iterdir()) == ["InstrumentSerif-Regular.ttf", "OFL.txt"], folder


# The Android theme: every brand's is written under Brasscribe's names until the Android apps use the neutral ones.

def test_fretscribe_theme_has_the_names_the_shared_screens_use():
    # The apps share their screens, so both generated themes declare exactly the same names.
    for name in ("BrasscribeTheme.kt", "BrasscribeIcon.kt", "ScribeTheme.kt"):
        ours = (build.DIST / KOTLIN / name).read_text()
        theirs = (FRETSCRIBE / "dist" / KOTLIN / name).read_text()
        assert len(declarations(ours)) > 15, name
        assert declarations(theirs) == declarations(ours), name
    assert sorted(p.name for p in (FRETSCRIBE / "dist" / "android" / "res" / "drawable").iterdir()) == \
        sorted(p.name for p in (build.DIST / "android" / "res" / "drawable").iterdir() if not p.name.startswith("ic_launcher"))


def test_fretscribe_roles_come_through_the_alias_map():
    fs = fretscribe()
    kt = (FRETSCRIBE / "dist" / KOTLIN / "BrasscribeTheme.kt").read_text()
    light = kt.split("val BrasscribeLightColors = BrasscribeColors(")[1].split(")\n\n")[0]
    for field, role in (("brass", "brand"), ("brassText", "brand-text"), ("brassTint", "brand-tint"), ("staff", "string"),
                        ("veryUncertain", "uncertain"), ("adlibTint", "loop-tint"), ("primary", "primary")):
        assert f"    {field} = Color({fs.argb(fs.hexval('light', role), fs.alpha('light', role))})," in light, field
    # No Pink palette: the pink values are the standard ones.
    pink = kt.split("val BrasscribePinkColors = BrasscribeColors(")[1].split(")\n\n")[0]
    dark = kt.split("val BrasscribeDarkColors = BrasscribeColors(")[1].split(")\n\n")[0]
    pink_dark = kt.split("val BrasscribePinkDarkColors = BrasscribeColors(")[1].split(")\n\n")[0]
    assert pink == light and pink_dark == dark and light != dark
    # The titles: the brand's own face, at the weight its display token names.
    assert "displaySmall = base.displaySmall.copy(fontFamily = display, fontWeight = FontWeight.SemiBold," in kt
    font = FRETSCRIBE / "dist" / "android" / "res" / "font" / "atkinson_hyperlegible_next.ttf"
    assert font.read_bytes() == (FRETSCRIBE / "brand" / "fonts" / "AtkinsonHyperlegibleNext-wght.ttf").read_bytes()


def test_android_neutral_names_read_the_theme():
    for b in brands().values():
        kt = (b.DIST / KOTLIN / "ScribeTheme.kt").read_text()
        assert "typealias ScribeColors = BrasscribeColors" in kt
        for neutral, own in (("brand", "brass"), ("brandText", "brassText"), ("brandTint", "brassTint"), ("line", "staff")):
            assert f"val ScribeColors.{neutral}: Color get() = {own}\n" in kt
        assert "get() = LocalBrasscribeColors.current" in kt and "pink" not in kt.lower()


def test_android_window_colours_are_the_token_backgrounds():
    # The window behind Compose (apps/android, each product's res/values/themes.xml) is the token bg.
    import re
    app = build.ROOT / "apps" / "android" / "app" / "src"
    fs = fretscribe()
    for product, tokens, modes in (("brasscribe", build, ("light", "dark", "pink", "pink-dark")),
                                   ("fretscribe", fs, ("light", "dark", "light", "dark"))):
        xml = (app / product / "res" / "values" / "themes.xml").read_text()
        found = dict(re.findall(r'<color name="(window_\w+)">#FF([0-9A-F]{6})</color>', xml))
        want = dict(zip(("window_light", "window_dark", "window_pink", "window_pink_dark"),
                        (tokens.hexval(m, "bg")[1:] for m in modes)))
        assert found == want, product


def test_another_product_writes_only_into_its_own_folder(tmp_path):
    fs = product_build(FRETSCRIBE / "tokens" / "tokens.json", tmp_path / "dist")
    want = fs.outputs()
    assert want and all(p.is_relative_to(tmp_path / "dist") for p in want)
    fs.write()
    assert fs.stale() == []
    assert build.stale() == []  # Brasscribe's outputs are untouched


def test_a_brand_cannot_use_another_brands_folder():
    import pytest
    # The folder's owner is named, and so is the token file that needs another.
    with pytest.raises(SystemExit, match=r"design/dist is the output folder of brasscribe .*give design/fretscribe/tokens/tokens.json its own --out"):
        product_build(FRETSCRIBE / "tokens" / "tokens.json", build.DEFAULT_DIST)
    with pytest.raises(SystemExit, match=r"design/fretscribe/dist is the output folder of fretscribe .*give design/tokens/tokens.json its own --out"):
        product_build(build.DEFAULT_TOKENS, FRETSCRIBE / "dist")


def test_a_role_the_product_neither_has_nor_maps_is_an_error(tmp_path):
    import pytest
    fs = product_build(broken(tmp_path, lambda raw, ext: ext["android"]["aliases"]["roles"].pop("staff")), tmp_path / "dist", "android")
    with pytest.raises(SystemExit, match="no role for 'staff'"):
        fs.outputs()
