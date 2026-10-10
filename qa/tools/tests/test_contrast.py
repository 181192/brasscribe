import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import contrast as c  # noqa: E402


def test_contrast_extremes():
    assert round(c.contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(c.contrast("#777777", "#FFFFFF"), 2) == 4.48


def test_ciede2000_reference_pair():
    # Sharma et al. (2005) test data, pair 1: 2.0425
    assert abs(c.ciede2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)) - 2.0425) < 1e-3


def test_simulation_keeps_greys():
    grey = c.simulate((0.5, 0.5, 0.5), "deutan")
    assert all(abs(x - 0.5) < 0.01 for x in grey)


def test_dtcg_tokens_load_and_pass():
    tokens = c.ROOT / "design" / "tokens" / "tokens.json"
    if not tokens.exists():
        return
    data = c.load_dtcg(tokens)
    assert set(data["themes"]) == {"light", "dark", "high-contrast", "high-contrast-light", "pink", "pink-dark"}
    for theme in data["themes"].values():
        for fg, bg, minimum, _ in data["pairs"]:
            assert c.contrast(theme[fg], theme[bg]) + 1e-9 >= minimum, (fg, bg)


def test_fretscribe_tokens_load_and_pass():
    tokens = c.ROOT / "design" / "fretscribe" / "tokens" / "tokens.json"
    data = c.load_dtcg(tokens)
    assert set(data["themes"]) == {"light", "dark", "high-contrast", "high-contrast-light"}
    assert data["pairs"]
    for theme in data["themes"].values():
        for fg, bg, minimum, _ in data["pairs"]:
            assert c.contrast(theme[fg], theme[bg]) + 1e-9 >= minimum, (fg, bg)
    assert c.main(["--tokens", str(tokens)]) == 0


def test_dtcg_extension_namespace_is_not_fixed(tmp_path):
    token = {"$type": "color", "$value": {"colorSpace": "srgb", "components": [0, 0, 0], "hex": "#000000"}}
    paper = {"$type": "color", "$value": {"colorSpace": "srgb", "components": [1, 1, 1], "hex": "#FFFFFF"}}
    raw = {"$extensions": {"org.example.other": {"note": "not ours"},
                           "no.example": {"modes": ["light"],
                                          "contrast": {"pairs": [["ink", "bg", 4.5, "1.4.3"]], "distinguish": []}}},
           "color": {"light": {"ink": token, "bg": paper}}}
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(raw))
    data = c.load_dtcg(path)
    assert data["themes"] == {"light": {"ink": "#000000", "bg": "#FFFFFF"}}
    assert data["pairs"] == [["ink", "bg", 4.5, "1.4.3"]]


def test_every_brand_passes_in_every_mode_and_its_report_is_current(capsys):
    # design/tokens/brands.json lists the brands; each has at least the four neutral modes.
    assert {b["name"] for b in c.brands()} >= {"brasscribe", "fretscribe"}
    for brand in c.brands():
        data = c.load_dtcg(c.ROOT / brand["tokens"])
        assert set(data["themes"]) >= {"light", "dark", "high-contrast", "high-contrast-light"}, brand["name"]
        for mode, theme in data["themes"].items():
            for fg, bg, minimum, _ in data["pairs"]:
                assert c.contrast(theme[fg], theme[bg]) + 1e-9 >= minimum, (brand["name"], mode, fg, bg)
    assert c.main(["--brands"]) == 0, capsys.readouterr().out


def test_a_malformed_brand_is_told_what_is_missing(tmp_path, monkeypatch):
    import pytest
    listed = tmp_path / "brands.json"
    monkeypatch.setattr(c, "BRANDS", listed)
    listed.write_text(json.dumps({"brands": [{"name": "x", "tokens": "design/tokens/tokens.json"}]}))
    with pytest.raises(SystemExit, match="brand x has no 'contrast-report'"):
        c.main(["--brands"])
    listed.write_text(json.dumps({"brands": [{"name": "x", "tokens": "nowhere.json", "contrast-report": "r.md"}]}))
    with pytest.raises(SystemExit, match="x's token file nowhere.json is not there"):
        c.main(["--brands"])
    raw = json.loads((c.ROOT / "design" / "tokens" / "tokens.json").read_text())
    raw["$extensions"]["no.brasscribe"]["contrast"]["pairs"].append(["glow", "bg", 3.0, "1.4.11"])
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps(raw))
    with pytest.raises(SystemExit, match="a contrast pair names 'glow', which color.light does not have"):
        c.load_dtcg(tokens)
