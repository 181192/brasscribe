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
