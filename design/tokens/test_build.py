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
    assert f'{more} {{\n  :root:not([data-theme="dark"]) {{\n    color-scheme: light;\n    --bc-bg: #FFFFFF;' in css
    assert f'{more} and (prefers-color-scheme: dark) {{\n  :root:not([data-theme="light"]) {{\n    color-scheme: dark;\n    --bc-bg: #000000;' in css
    assert f'{more} {{\n  :root[data-theme="dark"] {{\n    color-scheme: dark;\n    --bc-bg: #000000;' in css


def test_pink_keeps_the_notation_and_its_meaning():
    # Pink recolours the chrome only: the notation stays black on light (paper tones on dark) and the
    # score hues keep their meaning.
    for pink, base in (("pink", "light"), ("pink-dark", "dark")):
        for role in ("ink", "staff", "uncertain", "very-uncertain", "loop-edge", "cursor", "success", "warning", "brass"):
            assert build.hexval(pink, role) == build.hexval(base, role), (pink, role)


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
    assert ':root[data-palette="pink"] {\n    color-scheme: light;\n    --bc-bg: #FFF6F9;' in css
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
    assert xaml.index('<Color x:Key="BcBgColor">#FFFFF6F9</Color>') in range(light, dark)
    assert xaml.index('<Color x:Key="BcPrimaryColor">#FFFF9ECF</Color>') > dark
    assert 'x:Key="HighContrast"' in xaml


# ---------------------------------------------------------------- another product: Fretscribe's Android theme

FRETSCRIBE = build.ROOT / "design" / "fretscribe"


def product_build(tokens: Path, out: Path):
    """A second copy of the generator set up for another product, so `build` stays Brasscribe's."""
    s = importlib.util.spec_from_file_location("design_build_product", HERE / "build.py")
    module = importlib.util.module_from_spec(s)
    s.loader.exec_module(module)
    module.configure(tokens, out, "android")
    return module


def fretscribe():
    return product_build(FRETSCRIBE / "tokens" / "tokens.json", FRETSCRIBE / "dist")


def declarations(kotlin: str) -> list[str]:
    """Every declared name of a generated Kotlin file, in order: types, functions, values and fields."""
    import re
    return re.findall(r"^\s*(?:@\w+\s+)*((?:data class|enum class|object|fun|const val|val)\s+[\w.]+|[A-Z_]+(?=\())", kotlin, re.M)


def test_fretscribe_outputs_in_sync():
    stale = fretscribe().stale()
    assert not stale, ("run `uv run design/tokens/build.py --tokens design/fretscribe/tokens/tokens.json "
                       "--out design/fretscribe/dist --only android`; stale: " + ", ".join(stale))


def test_fretscribe_every_mode_defines_every_role():
    fs = fretscribe()
    light = set(fs.roles())
    for mode in fs.MODES:
        assert set(k for k in fs.TOKENS["color"][mode] if not k.startswith("$")) == light, mode


def test_fretscribe_theme_has_the_names_the_shared_screens_use():
    # The apps share their screens, so both generated themes declare exactly the same names.
    for name in ("BrasscribeTheme.kt", "BrasscribeIcon.kt"):
        ours = (build.DIST / "android" / "kotlin" / "no" / "brasscribe" / "design" / name).read_text()
        theirs = (FRETSCRIBE / "dist" / "android" / "kotlin" / "no" / "brasscribe" / "design" / name).read_text()
        assert len(declarations(ours)) > 20, name
        assert declarations(theirs) == declarations(ours), name
    assert sorted(p.name for p in (FRETSCRIBE / "dist" / "android" / "res" / "drawable").iterdir()) == \
        sorted(p.name for p in (build.DIST / "android" / "res" / "drawable").iterdir() if not p.name.startswith("ic_launcher"))


def test_fretscribe_roles_come_through_the_alias_map():
    fs = fretscribe()
    kt = (FRETSCRIBE / "dist" / "android" / "kotlin" / "no" / "brasscribe" / "design" / "BrasscribeTheme.kt").read_text()
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
    assert want and all(p.is_relative_to(tmp_path / "dist" / "android") for p in want)
    fs.write()
    assert fs.stale() == []
    assert build.stale() == []  # Brasscribe's outputs are untouched


def test_another_product_cannot_use_brasscribes_dist_or_other_platforms():
    import pytest
    tokens = FRETSCRIBE / "tokens" / "tokens.json"
    with pytest.raises(SystemExit, match="its own --out"):
        product_build(tokens, build.DEFAULT_DIST)
    s = importlib.util.spec_from_file_location("design_build_product", HERE / "build.py")
    module = importlib.util.module_from_spec(s)
    s.loader.exec_module(module)
    with pytest.raises(SystemExit, match="--only android"):
        module.configure(tokens, FRETSCRIBE / "dist", None)


def test_a_role_the_product_neither_has_nor_maps_is_an_error(tmp_path):
    import pytest
    raw = json.loads((FRETSCRIBE / "tokens" / "tokens.json").read_text())
    del raw["$extensions"]["no.fretscribe"]["android"]["aliases"]["roles"]["staff"]
    (tmp_path / "tokens").mkdir()
    tokens = tmp_path / "tokens" / "tokens.json"
    tokens.write_text(json.dumps(raw))
    fs = product_build(tokens, tmp_path / "dist")
    with pytest.raises(SystemExit, match="no role for 'staff'"):
        fs.outputs()
